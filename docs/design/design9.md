# System Architecture & Runtime Design

[design8.md](design8.md) is frozen at the domain-contract level. This document does not introduce new domain concepts — it answers how the contracts defined there are actually built and operated: physical data placement, ingestion, graph mechanics, runtime paths, service boundaries, execution, correlation, failure handling, security, lifecycle, and operational guarantees.

## Physical Architecture

```text
                         ┌─────────────────────────┐
                         │      SOURCE SYSTEMS      │
                         │ Git / CI / Docs / APIs   │
                         │ Telemetry / Incidents    │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │        INGESTION         │
                         │ normalize / dedupe /     │
                         │ provenance / idempotency │
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │   KNOWLEDGE / EVIDENCE  │
                         │ Graph + Claims + Index  │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │      INTELLIGENCE        │
                         │ Impact → Risk            │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │        DECISION          │
                         │ Policy + Planner         │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │        EXECUTION         │
                         │ CI / tests / canary /    │
                         │ monitoring / deployment  │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │         OUTCOMES         │
                         │ validation + production  │
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │       EVALUATION         │
                         │ replay / learning /      │
                         │ model promotion          │
                         └──────────────────────────┘
```

**Governing principle for everything below:** design8 defines logical responsibilities, not deployment units. Whether a responsibility becomes an independent service is a *consequence* of scaling characteristics, failure isolation, data ownership, deployment cadence, latency requirements, and security boundaries — never an assumption made up front. §5 applies this explicitly.

---

## 1. Physical Data Architecture

design8 §25 already warns that the Knowledge Graph is the canonical *semantic* model, not the physical home for every artifact. Concretely:

| Contract objects | Storage category | Rationale |
| --- | --- | --- |
| `Entity`, `Relationship`, `Claim` | Temporal graph store | Native fit for traversal queries ("what does this change affect?"); needs bi-temporal (`valid_from/valid_to` + `observed_at`) support |
| `Evidence` | Evidence index (searchable, document-oriented) | Queried by subject/source_type/time, not by graph traversal; `source_ref` points *into* other systems rather than duplicating them |
| Source code, CI logs, diffs | Object/artifact storage | Large, immutable blobs; referenced via `source_refs[]`, never copied into the graph |
| Traces, metrics | Existing telemetry system | Platform is a read-only consumer; owning this data is out of scope |
| Incidents | Existing incident system (or a thin platform-owned mirror) | Same reasoning as telemetry — correlate, don't own |
| `DecisionContext`, `ImpactAssessment`, `RiskAssessment`, `ValidationDecision`, `Outcome`, `ResidualRiskAssessment`, `DecisionAuditRecord`, `Override`, `LearningSignal` | Append-only decision store | Immutability (design8 §16) is a storage-layer guarantee here, not an application convention — see §14 |
| `model_versions[]` | Model registry | Standard ML infra concern, referenced from `DecisionContext` |

**Consequence:** there is no single "the database." The graph store answers structural questions; the evidence index answers provenance questions; the decision store answers audit/reproducibility questions. Cross-references are by ID, not by data duplication.

---

## 2. Ingestion Architecture

Ingestion is the boundary where source-system data becomes `Entity` / `Relationship` / `Claim` / `Evidence` objects.

* **Normalization** — each source type (Git, CI, OpenAPI, traces, incidents) has its own adapter producing the canonical shapes from §4/§6/§7 of design8; adapters are the only place that knows source-specific formats.
* **Deduplication** — a default idempotency key of `(source_type, source_ref, observed_at)` covers most sources (re-ingesting the same trace batch or the same PR diff is a no-op), but this default is not assumed globally sufficient — some sources can legitimately emit multiple distinct observations for the same reference and timestamp. Each adapter is responsible for producing the canonical idempotency key for its source type; the default is a starting point, not a platform-wide contract.
* **Provenance** — every ingested record carries its adapter version and source reference forward into the `Evidence.provenance` field — never dropped or flattened during normalization.
* **Backfill** — the same adapters must be runnable against historical data (bounded by the `valid_from`/`observed_at` they report) to support offline replay (design8 §22). Backfill is not a separate code path — it's the same ingestion pipeline pointed at historical input.

---

## 3. Graph Architecture

* **Bi-temporal model** — every `Relationship`/`Claim` carries `observed_at` (when we learned it) and `valid_from`/`valid_to` (when it was true), per design8 §24. These are independent axes: something can be observed today about what was true last January.
* **Snapshots** — `DecisionContext.graph_snapshot` is a **query parameter** (an as-of timestamp/version), not necessarily a physical copy of the graph. Physical snapshotting (materialized copies) is an optimization for replay performance, not a semantic requirement.
* **Mutation semantics** — the graph is **append-only at the relationship/claim level**. Nothing is edited in place; a changed belief creates a new `Claim` and marks the prior one `SUPERSEDED` (design8 §6), with `valid_to` set. This is what makes `DecisionContext` immutability (§16) actually hold — if graph writes were in-place mutations, "as of graph_snapshot X" would stop being a stable statement.

---

## 4. Decision Runtime: Synchronous vs. Asynchronous

Not every step in the design8 chain has the same latency budget.

**Synchronous critical path** (blocks CI, needs to complete before a PR can proceed):
```text
Change ingested → ImpactAssessment → RiskAssessment → ValidationDecision
```

**Asynchronous enrichment** (improves future decisions, never blocks the current one):
```text
Deep evidence gathering (e.g. re-running trace analysis)
Historical-similarity computation
BusinessFlow re-inference as traffic patterns shift
LearningSignal processing and model evaluation
```

**Consequence:** the synchronous path must be able to produce a `RiskAssessment` using *whatever Claims currently exist* — it never blocks waiting for a slow enrichment job. If a Claim is stale or missing, that shows up as lower `evidence_confidence` (design8 §10), not as a stalled pipeline. This is the direct architectural payoff of separating Evidence/Claim confidence from raw observation in design8 §6.

---

## 5. Service Boundaries

Applying the governing principle above to design8's logical responsibilities, a reasonable starting grouping — explicitly revisable as scaling data comes in:

| Grouping | Includes | Why grouped |
| --- | --- | --- |
| **Knowledge Service** | Graph store, Claims, Evidence index | Shared consistency *contract*, not necessarily a shared database transaction — see invariant below |
| **Intelligence Service** | Impact engine, Risk engine | Both are synchronous-path, read-heavy against the Knowledge Service, share the same latency budget |
| **Decision Service** | Policy engine, Validation Planner | Policy changes must affect planning atomically; separating them risks a planner acting on stale policy |
| **Execution Orchestrator** | CI adapter, canary/monitoring integration | Different failure domain (external systems: CI runners, deployment infra) and bursty scaling tied to PR volume, not to decision volume |
| **Outcome & Learning Service** | Outcome correlation, LearningSignal processing, evaluation/replay | Asynchronous, batch-oriented, write-heavy — fundamentally different operational profile than the synchronous path above |

**Invariant (Knowledge Service):** the Claim/Evidence pairing is a *consistency contract*, not a physical transaction guarantee — the graph store and evidence index need not be the same database, and atomicity across them may not be achievable. The actual invariant is: **a Claim cannot become visible to consumers until its referenced Evidence is resolvable.** This can be implemented as a write-order guarantee (Evidence committed before the Claim referencing it is published) rather than a distributed transaction.

**What this is not:** a mandate to build five microservices on day one. It may start as two or three deployables (e.g., Knowledge+Intelligence colocated, since both are read-heavy and low-latency) and split later purely because a scaling or failure-isolation need appears — for example, if Execution Orchestrator's CI-runner flakiness starts affecting Decision Service availability, that's the signal to separate them, not a diagram.

---

## 6. Validation Execution

The platform does not run tests itself — it decides *what* should run and hands that off:

* `ValidationDecision.selected_validations[]` is translated by the Execution Orchestrator into concrete CI jobs / canary configurations / monitoring windows, via thin per-system adapters (GitHub Actions, Jenkins, a canary controller, a monitoring platform).
* Each adapter is responsible for reporting back an `Outcome` (design8 §13) in the platform's canonical shape — the orchestrator does not parse CI-specific formats outside the adapter boundary.
* Manual validation (`ValidationCandidate.type = MANUAL_VALIDATION`) is represented as a pending `Outcome` awaiting human input, not a special-cased workflow.

---

## 7. Outcome Correlation

Per the design8 §13 correction, production truth is an independent event stream, not something a validation Outcome produces. Concretely:

```text
Validation Outcome ──────┐
                          ├── correlation ──► Production Incident
Deployment ───────────────┤
Production Signals ───────┘
```

A **Correlation process** subscribes to `Outcome`, `Deployment`, and `ProductionSignal`/`Incident` events and joins them on affected entities and a time window. This process:

* Runs continuously, not on a per-Change basis — an Incident three weeks after deployment must still be joinable back to the original `Outcome`.
* Is the only writer of `Outcome.production_correlation` — and is explicitly allowed to populate this field *after* the Outcome was originally created, since it doesn't affect decision reproducibility (only evaluation, design8 §21).
* Is what makes false-negative detection (design8 §21) possible at all: a `PASSED` outcome with no correlation at evaluation time may still gain one later.

This asynchronous, continuously-running shape is locked in as-is — production truth must not be modeled as a child of validation, and no future revision should collapse the two back into a single synchronous write.

---

## 8. Idempotency and Retries

* **Ingestion** — idempotency key per §2 (`source_type`, `source_ref`, `observed_at` hash); safe to replay any adapter run.
* **State machine transitions** (design8 §17) — re-processing a `CHANGE_FOUND` event for an already-analyzed `Change` is a no-op keyed on `change_id`; re-entering `VALIDATION_PLANNING` after a crash re-reads the existing `RiskAssessment` rather than recomputing it, unless it has been superseded by a new `DecisionContext`.
* **Validation execution** — outcomes are keyed on `(change_ref, validation_id, attempt_number)` so a CI retry produces a new attempt record rather than overwriting or duplicating the original `Outcome`.

---

## 9. Failure / Degraded Modes

| Component unavailable | Behavior |
| --- | --- |
| Knowledge Graph | Cannot create a new `DecisionContext` — synchronous path fails closed; policy default should require full validation rather than proceed with a stale/missing assessment |
| Telemetry / evidence sources | Do not block — proceed with reduced `evidence_confidence` (design8 §10); this is exactly what the confidence decomposition is for |
| Model serving (Intelligence Plane) | Fall back along the explicitly-permitted evolution path (design8 §18): `ML model → statistical model → rules` — never blocks, degrades in sophistication instead |
| Validation execution infra (CI/canary) | Escalate to manual validation or `ESCALATE` recommendation (design8 §14) rather than silently skipping validation |

The common pattern, stated precisely: **the decision path must never silently proceed with missing critical knowledge. Degradation is allowed only when the resulting decision explicitly reflects the loss of evidence/confidence and remains policy-valid** — a lower `evidence_confidence` or a fallback model version is acceptable because it is visible in the `RiskAssessment` and still subject to `RiskPolicy` thresholds (design8 §15); silently proceeding as if nothing were missing is not. The Knowledge Graph is simply the one dependency where no degraded substitute exists — there is no lower-confidence graph to fall back to — which is why it is the sole case that blocks outright rather than degrading.

---

## 10. Security and Tenancy

* `tenant_scope` (design8 §4.2) is enforced at every read/write boundary in the Knowledge Service — not as an application-level filter bolted on later.
* **Evidence visibility can be narrower than Claim visibility.** A cross-team impact analysis needs to know `ServiceA participates_in Checkout` with its confidence, but the owning team's raw production traces backing that Claim may be restricted. The architecture must support exposing a `Claim` (subject, predicate, object, confidence) across a tenancy boundary while keeping its underlying `Evidence` detail scoped to the owning team.
* Secrets and PII never enter the Knowledge Graph or Evidence index directly — `source_refs[]` point to systems that already have their own access control; the platform does not re-host sensitive payloads.

---

## 11. Data Lifecycle

* **Long retention (compliance/audit):** `DecisionContext`, `DecisionAuditRecord`, `Override` — these are the reproducibility and accountability record and should not be pruned on a normal data-retention schedule.
* **Prunable/archivable:** raw `Evidence` detail can move to cold storage once the `Claim` it supports has stabilized — the `evidence_refs[]` pointer and provenance metadata are retained; the bulky observation payload is not required to stay hot. **Constraint:** archival must never make a `DecisionContext` non-replayable within its declared retention window (§12) — the evidence index may hold only a pointer, but the referenced historical artifact itself must remain recoverable from cold storage, not deleted. Archival changes storage tier, never replay guarantees.
* **Temporal graph reconstruction** only needs to reach as far back as the replay and audit retention requirements dictate (§12) — not indefinitely.

---

## 12. Operational SLOs

To be tuned with real data, but the categories that need targets before launch:

* **Decision latency** — p95 time for the synchronous path (§4) to produce a `ValidationDecision`, since this gates CI.
* **Availability** — of the Knowledge Service specifically, since its unavailability fails the synchronous path closed (§9).
* **Evidence freshness** — acceptable staleness before `evidence_confidence` degradation kicks in.
* **Replayability** — guarantee that any `Change` within the retention window (§11) can be replayed per design8 §22.

---

## 13. Model Lifecycle

* Versioning ties directly to `DecisionContext.model_versions[]` (design8 §16) — every prediction is attributable to an exact model version.
* Promotion is gated by the evaluation framework (design8 §21): a `model_update_candidate` (from `LearningSignal`, §20) is only promoted after offline replay shows it does not regress the north-star metric (validation cost removed without increasing false-negative rate).
* Rollback is trivial by construction: new `DecisionContext`s simply reference the prior `model_version`; old `DecisionContext`s remain valid and immutable regardless (§14), so rollback never requires rewriting history.

---

## 14. Audit Guarantees

`DecisionContext` and `DecisionAuditRecord` immutability (design8 §16, §19) is enforced at the storage layer — the decision store exposes append/read APIs only, with no update or delete path for these object types. An `Override` (design8 §17) is always a new record referencing the original decision; it is architecturally impossible to overwrite what the system originally recommended.

---

## 15. Capacity / Scaling

Deliberately last, per the governing principle — scaling is assessed once the runtime and data flows above are real, not designed in the abstract. The known future scaling questions to revisit once there's traffic data:

* Graph query load at PR-analysis time (synchronous path, §4).
* Evidence ingestion volume from continuous telemetry streams (§2).
* Cost/latency of LLM-based inference steps (BusinessFlow inference, historical-similarity scoring) — candidates for the asynchronous path (§4) specifically because of this.

---

## Summary

This document answers the physical/runtime questions design8 deliberately deferred, without introducing new domain concepts. **design9.md is frozen alongside design8.md** as of this revision — the design series (design1.md–design9.md) is a committed baseline; further architectural change should come from what a real implementation exposes, not from further speculation about databases, queues, model providers, or scaling numbers.

The next artifact is not design10.md. It is a first vertical slice proving the chain end to end on a single repository:

```text
PR → Change → Knowledge snapshot → ImpactAssessment → RiskAssessment
   → RiskPolicy → ValidationDecision → one real validation → Outcome
```

exercising, at minimum: a deterministic `DecisionContext`, idempotent ingestion, a temporal graph query, an auditable decision, the explicit no-validation path, an infrastructure-failure retry, a human `Override` without mutation, and a later production correlation. Whatever that slice breaks is the real design10.md — grounded in what the architecture actually got wrong, not in further hypotheticals.
