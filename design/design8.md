# Domain Contracts & Decision Architecture

## 1. Purpose

This document defines the domain contracts, decision semantics, lifecycle, and evaluation framework for the **Software Change Intelligence Platform**, centered around a temporal **Software Change Knowledge Graph**. It freezes the conceptual architecture established in [design7.md](design7.md) and makes its core objects and decisions precise enough to implement independently.

The graph is not the product. The product is:

```text
Knowledge + Intelligence + Decision + Validation + Outcome + Learning
```

The graph is the persistent semantic memory connecting all of them. This distinction matters for design9: the goal is a change-risk decision system, not a graph platform.

Where design1.md–design7.md answered *what should the platform be*, this document answers: **what exactly flows through the platform, what does each component promise, and how do we know whether its decisions are correct?**

Every contract below is written so that an engineer can implement it without reinterpreting intent, and so that a decision can be reproduced exactly from a recorded snapshot of its inputs.

---

## 2. Design Principles

1. The **Knowledge Graph is the canonical system model** — no component holds a private, divergent view of reality.
2. **Observation, Evidence, Claim, and Decision are distinct layers** — raw fact, provenance-bearing support, interpreted belief, and acted-upon conclusion must never collapse into one number (see §6–§7).
3. **AI produces hypotheses/interpretations, not unbounded authority** — AI output is always evidence-checked before it becomes a Claim, and a Claim before it becomes a decision input.
4. **Risk is multi-dimensional, not a single score** — probability, business impact, exposure, and confidence are reported separately; no universal "risk score" is derived by this platform.
5. **Validation exists to reduce residual risk** — not to run tests for their own sake; "no validation needed" is a valid, explicitly represented output.
6. **Every important decision is auditable and reproducible** from a recorded `DecisionContext` (§16) — including human overrides, which are recorded, never silently applied as state mutations.
7. **Prediction and outcome are stored separately**, and every outcome — not only failures — produces a typed learning signal (§23).
8. **All learning is evaluated against observed reality**, including production outcomes the platform never saw as a test failure (§21).

---

## 3. Canonical Domain Model

**Frozen decision loop:**

```text
                 KNOWLEDGE
                     │
                     ▼
                  IMPACT
                     │
                     ▼
                   RISK
                     │
                     ▼
                 EVIDENCE
                     │
                     ▼
                VALIDATION
                     │
                     ▼
                  OUTCOME
                     │
                     ▼
              RESIDUAL RISK
                     │
                     ▼
                 LEARNING
                     │
                     └──────► KNOWLEDGE
```

**Frozen five-question mental model (the four-plane architecture, corrected):**

```text
Knowledge:     "What do we know?"        → Knowledge Plane
Intelligence:  "What do we believe?"     → Intelligence Plane
Decision:      "What should we do?"      → Decision Plane   (Policy lives HERE, not Intelligence)
Execution:     "What happened?"          → Execution Plane
Learning:      "What should we change about future beliefs?"
```

```text
                    ┌─────────────────────┐
                    │   KNOWLEDGE PLANE   │  Graph + Evidence + Claims
                    └──────────┬──────────┘
                               ▼
                    ┌─────────────────────┐
                    │ INTELLIGENCE PLANE  │  Impact + Risk inference
                    └──────────┬──────────┘
                               ▼
                    ┌─────────────────────┐
                    │    DECISION PLANE   │  Policy + Validation Planning
                    └──────────┬──────────┘
                               ▼
                    ┌─────────────────────┐
                    │   EXECUTION PLANE   │  Tests + Canary + Deployment
                    └──────────┬──────────┘
                               ▼
                           Outcomes
                               │
                               └──────► Knowledge Plane (via Learning)
```

Policy was previously grouped conceptually near Intelligence in earlier drafts; it belongs in the Decision Plane, since it converts belief into requirement (§15).

Everything in sections 4–15 is either a **node/edge/claim in the Knowledge Graph** or a **decision object** produced and consumed along this loop.

---

## 4. Entity Definitions

### 4.1 Canonical Entity List (unchanged — do not expand without implementation necessity)

```text
Organization, Team, Repository, RepositoryVersion, Commit, PullRequest, Change,
File, Symbol, Function, Class, Service, API, Event, Message, DataEntity, Schema,
FeatureFlag, BusinessCapability, BusinessFlow, BusinessOperation, Test, TestSuite,
Deployment, Environment, Incident, Failure, ProductionSignal, Owner
```

### 4.2 The Generic Entity Contract (strengthened)

Every entity in the graph, regardless of type, conforms to both a conceptual shape and a concrete field set:

```text
Entity (conceptual)
├── Identity      — globally unique id, stable across renames where possible
├── Purpose       — what this entity type represents (fixed per type, not per instance)
├── Required fields
├── Optional fields
├── Lifecycle     — created / active / deprecated / removed
├── Versioning    — how instances of this type change over time
└── Relationships — which relationship_types this entity may participate in

Entity (concrete, applies to every instance regardless of type)
├── entity_id
├── entity_type
├── tenant_scope
├── lifecycle
├── valid_from
├── valid_to
└── source_refs[]
   (plus type-specific fields, see §4.3)
```

`tenant_scope` and `valid_from`/`valid_to` are mandatory on every entity, not only on relationships — this is what makes multi-tenancy and temporal replay (§20, §24) possible without per-entity special-casing.

### 4.3 Representative Entity Schemas

(Unchanged from the prior draft — `Change`, `Service`, `BusinessFlow`, `Incident` remain the only entities given bespoke schemas; the rest instantiate from §4.2.)

#### Object: `Change`
```text
Change
├── change_id
├── repository_id
├── pull_request_ref
├── commit_shas[]
├── author
├── changed_files[]
├── changed_symbols[]
├── diff_ref
├── change_types[]
├── created_at
└── graph_version_at_ingest
```
**Invariant:** `graph_version_at_ingest` must equal the `graph_snapshot` recorded in the first `DecisionContext` (§16) created for this Change.

#### Object: `Service`
```text
Service
├── service_id
├── name
├── repository_id
├── owner_team_id
├── environment_refs[]
├── criticality
├── version
└── metadata
```

#### Object: `BusinessFlow`
```text
BusinessFlow
├── flow_id
├── name
├── steps[]
├── owning_capability_id
├── criticality
└── metadata
```

#### Object: `Incident`
```text
Incident
├── incident_id
├── detected_at
├── affected_services[]
├── affected_flows[]
├── severity
├── root_cause_ref
├── related_change_ref
└── resolution_ref
```

---

## 5. Relationship Model

### Object: `Relationship`

**Purpose:** A typed, structural, **graph-indexable projection** of a `Claim` (§6) — it exists so the graph store can traverse "what connects to what" efficiently. It is not a second, independent source of truth about belief or validity.

**`Relationship` is derived, not authored (invariant — closes the ambiguity identified in architect review):**

```text
Claim created/superseded
        │
        ▼
Relationship projection is (re)materialized from it
```

* `Relationship` carries **no independently authored semantic, validity, or confidence state.** Every field describing *whether this is true, how confident we are, or when it was/is valid* lives exclusively on the `Claim` referenced by `claim_ref`.
* `Relationship.observed_at`, `valid_from`, and `valid_to` are **copied from, and must always equal, the corresponding fields on the current `Claim`** — they exist on `Relationship` only to make the graph store's own indexes and traversal queries fast, not because `Relationship` independently decides temporal validity.
* When a `Claim` is superseded (§6 — `status: SUPERSEDED`, new `Claim` created), the `Relationship` projection is **re-materialized** to reflect the new `Claim`: this may mean updating the existing `Relationship`'s `claim_ref`/temporal fields to point at the new `Claim`, or retiring the old projection and creating a new one — either is an acceptable *implementation* of the same invariant, but neither implementation may leave a `Relationship` pointing at a `SUPERSEDED` Claim as if it were still current.
* **No component may write to `Relationship.valid_from`/`valid_to`/`observed_at` directly.** The only legitimate write path is: create or supersede a `Claim`, then re-derive the `Relationship` projection from it. This is what prevents `Relationship` and `Claim` from being interpreted, or implemented, as two independent sources of truth that can silently disagree.

**Schema:**
```text
Relationship
├── relationship_id
├── source_entity
├── relationship_type
├── target_entity
├── claim_ref
├── observed_at        # derived — mirrors claim_ref.Claim.observed equivalent
├── valid_from          # derived — mirrors claim_ref.Claim.valid_from
└── valid_to            # derived — mirrors claim_ref.Claim.valid_to
```

**Controlled relationship types (initial set):**
```text
Function ──calls──────────────> Function
Service ──contains────────────> Function
Service ──exposes─────────────> API
Service ──publishes───────────> Event
Event ──consumed_by───────────> Service
API ──participates_in─────────> BusinessFlow
BusinessFlow ──validated_by───> Test
Test ──produces───────────────> Outcome
Outcome ──correlated_with─────> Incident
Change ──affects──────────────> Entity
```

**Invariant:** A `Relationship` without a `claim_ref` is invalid — structure alone does not imply belief; belief comes from the referenced Claim, and only from the referenced Claim.

---

## 6. Claim Model *(new — replaces confidence/evidence fields formerly embedded in Relationship)*

### Object: `Claim`

**Purpose:** Makes the interpretive layer explicit and separates it from raw observation. This is the single most important correction to the prior draft: `Evidence.confidence = 0.94` was previously indistinguishable from objective truth. The corrected model:

```text
ENTITY
   ↓
CLAIM
   ↑
EVIDENCE
```

An `Evidence` object records what was observed. A `Claim` records what we now believe, backed by one or more pieces of Evidence, with its own confidence and lifecycle. Relationships, `ImpactAssessment.affected_entities[]`, and any other interpretive edge reference a Claim rather than embedding confidence themselves.

**Schema:**
```text
Claim
├── claim_id
├── subject
├── predicate
├── object
├── claim_type
├── status            # ACTIVE | SUPERSEDED | RETRACTED
├── confidence
├── evidence_refs[]
├── valid_from
├── valid_to
└── created_at
```

**Example:**
```text
Claim:
  PaymentService participates_in Checkout
  confidence: 0.93
  status: ACTIVE
  evidence_refs:
    - trace-182
    - api-spec-44
    - static-analysis-81
```

**Consumed by:** `Relationship.claim_ref`, `ImpactAssessment.affected_entities[].claim_ref` (see §9 update).

**Invariant:** `Claim.confidence` is derived from its supporting `Evidence` set via a **versioned claim-scoring function**, not an implied universal mathematical operation:

```text
Claim.confidence =
    versioned_aggregation_function(
        supporting Evidence,
        evidence strength,
        source reliability,
        temporal freshness
    )
```

`strength`, `reliability`, and freshness are the function's *inputs*, not a fixed `strength × reliability × freshness` formula — the exact aggregation function (and its version) is an implementation/model decision, left pluggable per §18. It is never authored directly by a human or model without at least one `evidence_ref`.

---

## 7. Evidence Model

### Object: `Evidence`

**Purpose:** The atomic, provenance-bearing record of an observation. Evidence supports Claims; it does not itself assert a belief or a confidence in that belief — that responsibility moved to `Claim` in §6.

**Schema:**
```text
Evidence
├── evidence_id
├── source_type
├── source_ref
├── observation
├── strength
├── reliability
├── observed_at
├── valid_from
├── valid_until
├── provenance
└── metadata
```

`confidence` has been removed from this object — it now lives exclusively on `Claim`, computed from the `strength` and `reliability` of the Evidence records that support it.

**Controlled `source_type` values:**
```text
STATIC_ANALYSIS, API_SPECIFICATION, SOURCE_CODE, TEST_EXECUTION, CI_RESULT,
DEPLOYMENT, TRACE, METRIC, LOG, INCIDENT, DOCUMENTATION, HUMAN_ASSERTION, AI_INFERENCE
```

**Field semantics:**
* `strength` — how directly the observation supports the claim it's attached to (a 1.8M-request production trace is stronger than one doc sentence).
* `reliability` — how trustworthy the source type is in general (traces > docs > AI inference, as a default prior).

**Invariant — the layered distinction that must never collapse:**
```text
Observation   ("we saw X happen")            → Evidence
    ≠
Inference     ("we believe X is true")       → Claim
    ≠
Decision      ("we will act as if X is true")→ ImpactAssessment / RiskAssessment / ValidationDecision
```
`AI_INFERENCE` evidence may exist, but a `Claim` backing a `CRITICAL`-impact relationship can never rest solely on `AI_INFERENCE` evidence — see the policy invariant in §15.

**Example:**
```text
Evidence set supporting the Claim in §6:
  trace-182:          source_type: TRACE, strength: 0.96, reliability: 0.95
  api-spec-44:        source_type: API_SPECIFICATION, strength: 0.70, reliability: 0.85
  static-analysis-81: source_type: STATIC_ANALYSIS, strength: 0.88, reliability: 0.90
```

**Produced by:** every analysis component (static analyzers, trace ingestion, test runners, LLM inference layers).

**Consumed by:** `Claim`.

---

## 8. Change Model

Defined in §4.3. `Change` is the sole entry point into the decision chain; every downstream contract carries a `change_ref` back to it.

---

## 9. Impact Assessment Contract

### Object: `ImpactAssessment`

**Purpose:** Answers "what might this change affect?"

**Schema:**
```text
ImpactAssessment
├── assessment_id
├── change_ref
├── affected_entities[]
├── affected_capabilities[]
├── affected_flows[]
├── impact_types[]
├── impact_confidence
├── uncertainty_sources[]
├── decision_context_ref
└── created_at
```

**Per-entity detail — `AffectedEntity`:**
```text
AffectedEntity
├── entity_ref
├── impact_type
├── impact_probability
├── claim_ref
└── rationale
```

**Example:**
```text
PR-123
  affects PaymentService     probability: 0.98   (claim confidence: 0.96)
  affects Checkout           probability: 0.91   (claim confidence: 0.87)
  affects SubscriptionRenewal probability: 0.42  (claim confidence: 0.54)
```

Note the change from the prior draft: `evidence_refs[]` and `analyzer_versions[]` are removed from this object — provenance now flows through `claim_ref` (§6), and versioning flows through `decision_context_ref` (§16) rather than being scattered per-object.

**Produced by:** Impact Analysis (deterministic dependency traversal + AI inference over the Knowledge Graph).

**Consumed by:** RiskAssessment.

**Invariant:** Every entry in `affected_entities[]` must carry a `claim_ref`, which in turn must carry at least one `evidence_ref` — an entity inferred with zero evidence is not included.

---

## 10. Risk Assessment Contract

### Object: `RiskAssessment`

**Purpose:** Answers "how likely and how consequential is a regression?" Kept strictly separate from Impact (what) and Evidence/Claim (why we believe it). **This platform does not compute or expose a universal risk score** — probability, impact, exposure, and confidence are reported as separate dimensions, and policy (§15) decides what to do with them.

**Schema:**
```text
RiskAssessment
├── assessment_id
├── change_ref
├── impact_assessment_ref
├── supporting_claim_refs[]
├── supporting_evidence_refs[]
├── probability
├── business_impact
├── exposure
├── risk_level
├── confidence
├── uncertainty_sources[]
├── decision_context_ref
└── created_at
```

**Provenance fields (added — closes the audit-chain gap identified in architect review):** `ImpactAssessment` carries a `claim_ref` per affected entity, so "why do we believe this is affected?" is always answerable. Prior to this revision, `RiskAssessment` had no equivalent — the chain of evidence stopped one hop too early. `impact_assessment_ref` points to the specific `ImpactAssessment` this risk was derived from; `supporting_claim_refs[]` and `supporting_evidence_refs[]` name the *specific* Claims and Evidence that actually informed `probability` and `probability_confidence` — not merely "everything in the `DecisionContext.evidence_snapshot`," which is the entire evidence state at that time, not the subset that mattered to this number. This is what makes "why is `probability_confidence` 0.64?" answerable from the `RiskAssessment` object itself, the same way §10's own debugging example implies it should be.

**`confidence` is decomposed, not a single opaque number:**
```text
confidence
├── impact_confidence
├── probability_confidence
├── evidence_confidence
└── overall
```

This decomposition exists so that when engineers ask "why?", the answer is immediate:
```text
Risk = HIGH
Risk confidence (overall) = 91%

Why?
  impact_confidence:     0.96
  probability_confidence: 0.64   ← the weak link
  evidence_confidence:    0.93
```

**Field semantics (precise, to prevent divergent model interpretations):**

* `probability` — *probability that the change introduces a material regression affecting the assessed scope under the relevant operating conditions.* Not "probability of any test failing."
* `business_impact` — controlled scale: `NONE | LOW | MEDIUM | HIGH | CRITICAL`.
* `exposure` — how much production surface/traffic/revenue sits behind the affected scope; a multiplier context for `business_impact`, not folded into `probability`.
* `confidence.overall` — confidence in *this assessment*, not the probability of failure. `Risk: Low, confidence.overall: 95%` and `Risk: Low, confidence.overall: 32%` are different states requiring different downstream handling (§15, §17).
* `risk_level` — a **policy/model-facing categorical classification derived from the multidimensional assessment**, not a numeric aggregation and not a reintroduction of the forbidden universal risk score:

```text
risk_level =
    policy/model classification of
    {probability, business_impact, exposure, confidence}

risk_level MUST NOT be treated as a substitute for its constituent dimensions.
```

`risk_level` exists purely as a convenient vocabulary (`LOW | MEDIUM | HIGH | CRITICAL`) for policy rules to key off of (§15) — any component reasoning about *why* a risk is what it is must read the underlying dimensions, never `risk_level` alone.

**Note on formula:** No formula (e.g. `probability × impact × confidence`) is fixed by this contract. `RiskAssessment` is a domain contract; the algorithm producing it is replaceable (rules today, a statistical or ML model later) — see §18.

**Invariant:** `supporting_claim_refs[]` must be non-empty whenever `probability > 0` is asserted on evidence rather than pure policy default — a `RiskAssessment` that cites no Claims is only valid as a default/floor assessment (e.g. "no impact detected, therefore minimal risk"), never as a substantive risk finding.

**Produced by:** Risk Engine.

**Consumed by:** ValidationDecision (via Policy).

---

## 11. Validation Candidate Contract

### Object: `ValidationCandidate`

**Purpose:** One possible action to acquire more evidence about a risk. Not synonymous with "test" — a candidate can be a test, a canary, or a monitoring window.

**Schema:**
```text
ValidationCandidate
├── validation_id
├── type
├── target_entities[]
├── target_risks[]
├── estimated_cost
├── estimated_duration
├── reliability
├── expected_outcome_distribution
├── expected_residual_risk
├── expected_information_gain
├── prerequisites[]
└── execution_parameters
```

**Controlled `type` values:**
```text
UNIT_TEST, INTEGRATION_TEST, CONTRACT_TEST, E2E_TEST, STATIC_ANALYSIS,
REPLAY, CANARY, MONITORING, MANUAL_VALIDATION
```

**The estimation interface (previously underspecified — now made explicit):**
```text
estimate(
    current_risk,
    candidate,
    evidence_state
)
    →
    predicted_outcome_distribution
    →
    expected_residual_risk
```

This is what `expected_residual_risk` and `expected_outcome_distribution` above are populated by. It replaces the earlier, uncombined trio of `expected_detection_probability` / `expected_information_gain` / `expected_risk_reduction` with a single, explicit prediction step whose output (`expected_residual_risk`) is directly comparable across candidates:

```text
Candidate A:  cost 5   →  expected_residual_risk 0.12
Candidate B:  cost 20  →  expected_residual_risk 0.04
```

**Validation Value (the ranking function the planner uses — see §18):**
```text
Validation Value =
    Expected Reduction in Decision-Relevant Residual Risk
    ──────────────────────────────────────────────────────
    Validation Cost
```

**Invariant:** `expected_information_gain` is an *input* to `estimate()`, never the optimization objective itself — a candidate can carry high information gain and still be low-value if that information isn't decision-relevant to the current risk. Risk reduction dominates; confidence improvement is secondary; raw information gain is tertiary.

**Produced by:** Candidate generation (test catalog + coverage mapping + canary/monitoring templates) plus the estimation function above.

**Consumed by:** ValidationDecision.

---

## 12. Validation Decision Contract

### Object: `ValidationDecision`

**Purpose:** The planner's actual choice — which candidates run, which don't, and why.

**Schema:**
```text
ValidationDecision
├── decision_id
├── change_ref
├── initial_risk
├── initial_confidence
├── target_residual_risk
├── required_confidence
├── candidate_validations[]
├── selected_validations[]
├── rejected_validations[]
├── estimated_cost
├── expected_risk_reduction
├── decision_reason
├── decision_context_ref
└── created_at
```

**Invariant:** Every entry in `rejected_validations[]` carries a `decision_reason` — rejection is a recorded decision, not an omission.

**The no-validation path is explicit, not implicit** (see corrected state machine, §17):
```text
VALIDATION_PLANNING
       │
       ├── validation required ──→ VALIDATING
       │
       └── sufficient confidence ─→ ACCEPTED     (selected_validations = [])
```
"No validation required" is itself a recorded decision with a `decision_reason`, not the absence of one.

**Produced by:** Validation Planner (optimizer, §18), constrained by Policy (§15).

**Consumed by:** Execution layer; Outcome; Audit (§19).

---

## 13. Outcome Contract

### Object: `Outcome`

**Purpose:** What actually happened when a `ValidationCandidate` was executed. **`result` (what happened) and `classification`/`cause` (why) are now separate fields** — the prior draft's single enum mixed "the test failed" with "why it failed" and buried a production incident inside the same enum as a test result.

**Schema:**
```text
Outcome
├── outcome_id
├── validation_ref
├── result
├── classification
├── cause_ref
├── evidence_refs[]
├── production_correlation
├── actual_impact
└── created_at
```

**Controlled `result` values (what happened, execution-level only):**
```text
PASSED | FAILED | DEGRADED | INCONCLUSIVE
```

**Controlled `classification` values (why it happened):**
```text
GENUINE_REGRESSION | FLAKY | INFRASTRUCTURE | ENVIRONMENT | PRE_EXISTING | DATA_ISSUE
```

**Production incidents are correlated with an Outcome, not caused by one.** The prior phrasing (`Outcome → Incident`) implied validation execution is what produces production truth — it isn't. Production observation is an **independent event stream** (deployments, production signals, incidents all occur on their own timeline), which may *later* correlate with a validation Outcome:

```text
Validation Outcome ──────┐
                          ├── correlation ──► Production Incident
Deployment ───────────────┤
Production Signals ───────┘
```

So the chain reads as correlation, not causation:
```text
Test FAILED  → classification: GENUINE_REGRESSION → Deployment proceeded → correlated_with → Incident
Test FAILED  → classification: INFRASTRUCTURE      → No deployment       → (no incident to correlate)
```
This distinction is particularly important for detecting false negatives (§21): a `PASSED` Outcome with no correlated Incident *at evaluation time* can still later correlate with one once production evidence arrives — the correlation is discovered, not decided at Outcome-creation time. design9 models this event stream and its correlation mechanism explicitly (§ physical/runtime architecture).

**Produced by:** Execution layer + Outcome classification (deterministic where possible; AI-assisted classification is evidence-checked per §2 principle 3).

**Consumed by:** ResidualRiskAssessment, LearningSignal (§23 — every classification produces a distinct signal type, not only `GENUINE_REGRESSION`).

---

## 14. Residual Risk Contract

### Object: `ResidualRiskAssessment`

**Purpose:** The system's actual stopping condition.

**Schema:**
```text
ResidualRiskAssessment
├── change_ref
├── prior_risk
├── observed_evidence[]
├── updated_probability
├── updated_confidence
├── residual_risk
├── remaining_uncertainty[]
├── recommendation
├── decision_context_ref
└── created_at
```

**Lifecycle this closes:**
```text
Initial Risk → Validation → Evidence → Updated Risk → Residual Risk
```

**Controlled `recommendation` values:** `ACCEPT | ESCALATE | REQUIRE_ADDITIONAL_VALIDATION`.

**Produced by:** Risk Engine, re-invoked with `Outcome` evidence added to the graph.

**Consumed by:** Decision state machine (§17), Policy (approval gates), LearningSignal.

---

## 15. Policy Contract

### Object: `RiskPolicy`

**Purpose:** Separates *what we believe* (Intelligence Plane) from *what we are required to do* (Decision Plane — see the corrected plane assignment in §3). Organization- and domain-configurable.

**Schema:**
```text
RiskPolicy
├── policy_id
├── organization_id
├── business_criticality_rules
├── risk_thresholds
├── confidence_thresholds
├── validation_requirements
├── deployment_requirements
├── escalation_rules
├── override_rules
└── version
```

**Responsibility chain:**
```text
Intelligence → produces assessment
Policy       → converts assessment into requirement
Planner      → selects actions satisfying requirement
```

**Key invariant:** A `RiskAssessment` with `confidence.overall` below a policy's `confidence_thresholds` can never be treated as equivalent to a high-confidence low-risk assessment, regardless of `risk_level`:
```text
IF business_impact = CRITICAL AND residual_risk > threshold
THEN require E2E + canary

IF risk = MEDIUM AND confidence.overall < 70%
THEN expand impact analysis   # investigate before optimizing
```

A `Claim` backing a `CRITICAL`-impact relationship resting solely on `AI_INFERENCE` evidence (§7) must fail this confidence threshold by policy default — enforced here, not just noted as a design aspiration.

**Produced by:** Organization/team configuration (human-authored, versioned).

**Consumed by:** ValidationDecision, ResidualRiskAssessment, approval/escalation gates.

---

## 16. Decision Context & Reproducibility *(new — promoted from scattered version fields)*

### Object: `DecisionContext`

**Purpose:** The single reproducibility anchor. Rather than scattering `graph_version`, `model_version`, and `policy_version` across every decision object (as the prior draft did), every decision references one `DecisionContext`.

**Schema:**
```text
DecisionContext
├── context_id
├── graph_snapshot
├── evidence_snapshot
├── policy_version
├── model_versions[]
├── candidate_catalog_version
└── timestamp
```

**Consumed by:** `ImpactAssessment.decision_context_ref`, `RiskAssessment` (add `decision_context_ref`), `ValidationDecision.decision_context_ref`, `ResidualRiskAssessment.decision_context_ref`.

**Invariant:** "Given the exact same `DecisionContext`, can I reproduce the decision?" must always be answerable yes — this is the reproducibility test from §19, now anchored to one object instead of several loosely-coordinated version fields.

**Invariant — immutability:** `DecisionContext` is immutable. A new graph state, evidence state, model version, policy version, or candidate-catalog version creates a **new** `DecisionContext`; it never mutates an existing one. Without this, reproducibility can quietly break even though every decision technically carries a `decision_context_ref`.

---

## 17. Decision Lifecycle / State Machine

```text
                    ┌──────────────┐
                    │ CHANGE_FOUND │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │ IMPACT       │
                    │ ASSESSMENT   │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │ RISK         │
                    │ ASSESSMENT   │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │ VALIDATION   │
                    │ PLANNING     │
                    └──────┬───────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
     validation required        sufficient confidence
              │                         │
              ▼                         ▼
      ┌──────────────┐            ┌──────────┐
      │  VALIDATING  │            │ ACCEPTED │  (selected_validations = [])
      └──────┬───────┘            └──────────┘
             ▼
      ┌──────────────┐
      │ OUTCOME      │
      │ COLLECTION   │
      └──────┬───────┘
             ▼
      ┌──────────────┐
      │ RESIDUAL     │
      │ RISK         │
      └──────┬───────┘
             ▼
   ┌────────────────────┐
   │ ACCEPT / ESCALATE  │
   └────────────────────┘
```

**Additional transitions:**

* `VALIDATING → VALIDATION_PLANNING` (retry) — on `classification: INFRASTRUCTURE` or `ENVIRONMENT`, re-plan rather than count as regression evidence.
* `RESIDUAL_RISK → VALIDATION_PLANNING` (loop) — when `recommendation = REQUIRE_ADDITIONAL_VALIDATION`, bounded by a max-iteration or cost-based cutoff in `RiskPolicy` (open decision, §27).
* **Human override is not a state transition** — see below.

**Human override, corrected:** the prior draft's `Any state → OVERRIDE` transition implied mutation of the system's decision. Instead:

### Object: `Override`
```text
Override
├── override_id
├── original_decision_ref
├── override_actor
├── override_reason
├── override_scope
├── override_timestamp
└── effective_decision_ref
```

The system's `ValidationDecision` (or `ResidualRiskAssessment`) is never modified. An `Override` is a new, separately auditable record whose `effective_decision_ref` points to what was actually done, while `original_decision_ref` preserves what the system recommended. This makes "engineers overrode the system's recommendation 18% of the time" a first-class, queryable evaluation signal (§21) rather than lost information.

---

## 18. Decision Algorithms

```text
RiskAssessment = f(
    Change,
    Impact,
    Evidence,
    HistoricalOutcomes,
    ProductionSignals
)

ValidationDecision = optimize(
    CandidateValidations,   # each pre-scored via estimate() from §11
    RiskAssessment,
    Policy
)
```

**Optimization objective:**
```text
Minimize:
    validation_cost

Subject to:
    residual_risk ≤ policy.risk_threshold
    confidence.overall ≥ policy.confidence_threshold
```

`optimize()` must support the empty selection (`selected_validations = []`) as its output when the unconstrained assessment already satisfies both constraints.

**Expected evolution path, explicitly permitted without contract changes:**
```text
rules → statistical model → ML model → hybrid model
```

---

## 19. Explainability & Audit Model

### Object: `DecisionAuditRecord`

**Purpose:** Every decision must be reproducible from a recorded snapshot.

**Schema:**
```text
DecisionAuditRecord
├── decision_ref
├── decision_context_ref
├── candidate_set
├── selected_actions
├── reasoning
└── timestamp
```

Note: `input_snapshot`, `evidence_snapshot`, `graph_version`, `model_version`, and `policy_version` from the prior draft are now carried via `decision_context_ref` (§16) rather than duplicated here.

**Invariant:** No `ValidationDecision`, `ResidualRiskAssessment`, or `Override` may be persisted without a corresponding `DecisionAuditRecord`.

---

## 20. Learning Contract

### Object: `LearningSignal`

**Purpose:** Converts an observed `Outcome` into a proposed model update — never a silent behavior change. **Every outcome classification produces a learning signal of the appropriate type** (corrected from the prior draft's narrower "only genuine regressions feed learning" — see §23).

**Schema:**
```text
LearningSignal
├── signal_id
├── prediction_ref
├── outcome_ref
├── signal_type
├── prediction_error
├── model_update_candidate
├── evidence_update[]
├── confidence_update[]
└── created_at
```

**Controlled `signal_type` values (mapped from `Outcome.classification`, §13):**
```text
INFRASTRUCTURE       → test-reliability signal
FLAKY                → test-flakiness signal
ENVIRONMENT          → environment-reliability signal
GENUINE_REGRESSION   → regression-pattern signal
(production incident, via production_correlation) → escaped-regression-pattern signal
```

**Invariant:** `model_update_candidate` requires evaluation (§21) before promotion to a `model_version` referenced by a future `DecisionContext`. Learning proposes; it does not deploy itself.

---

## 21. Evaluation Framework

**Per-change evaluation pipeline:**
```text
Prediction → Actual Outcome → Evaluation
```

**Metrics, by category:**

*Impact:* precision, recall, F1.

*Risk:* calibration (does a stated 20% probability regress ~20% of the time?), discrimination.

*Validation:* regression detection rate, tests executed, tests avoided, cost reduction.

*Production:* escaped regression rate, incident detection, customer-impact detection.

**Classification against ground truth — added, previously missing:**
```text
TRUE_POSITIVE   — platform flagged risk; a regression was real
TRUE_NEGATIVE   — platform declared sufficient confidence; no regression occurred
FALSE_POSITIVE  — platform flagged risk; no regression occurred
FALSE_NEGATIVE  — platform declared sufficient confidence; production later
                  demonstrated a material regression
```
`FALSE_NEGATIVE` is the platform's most important failure mode and must carry outsized weight in the learning/evaluation system — it is the case where "all selected tests passed → deployment → production regression" happens, and no test ever failed to signal it.

The bare label conflates several distinct root causes, so every `FALSE_NEGATIVE` evaluation record must decompose into which stage actually failed (evaluation metadata, not a new domain object):
```text
FALSE_NEGATIVE
├── missed_impact                 — the affected entity was never in ImpactAssessment
├── underestimated_probability    — impact was known, RiskAssessment.probability was too low
├── insufficient_validation       — risk was known, ValidationDecision didn't select enough coverage
├── validation_detection_failure  — the right validation ran but failed to detect the regression
└── production_detection_failure  — the regression was real but production monitoring missed it too
```
This decomposition is what makes the learning architecture (§20) able to target the actual weak stage rather than generically "running more tests."

**Validation regret — added, previously missing:**
```text
Validation regret =
    actual_validation_cost
    −
    minimum-cost validation that would have achieved the required confidence
```
This directly measures whether the optimizer (§18) is improving over time, independent of whether any particular change happened to regress.

**Override rate** (from §17) is tracked here as a trust metric: how often engineers overrode the system's recommendation, and in which direction (more validation vs. less).

**Baseline requirement:** every effectiveness/efficiency number is reported against a baseline (e.g., full test suite) — never in isolation.

**North-star metric:**
> How much validation cost did we remove without materially increasing escaped regression risk (i.e., without increasing the false-negative rate)?

---

## 22. Offline Replay

For each historical `PR-1 … PR-N`, replay using only information available *at the time* (per §24 — no June incident explaining a March decision). Reconstruct the graph and evidence state as of the `graph_snapshot` recorded in that change's original `DecisionContext` (§16), and ask:
```text
What would the platform have predicted?
What validation would it have selected?
Would it have detected the actual regression (per §21's TP/TN/FP/FN)?
How much validation cost would it have saved (validation regret)?
```

This is the required gate before the platform is granted autonomous CI/CD control.

---

## 23. Safety / Feedback Guardrails

Reframed from "what evidence feeds learning?" to **"what type of learning signal does each outcome classification produce?"** (§20) — this is strictly more powerful than the prior draft's single gate, because infrastructure and environment failures are not discarded, they're routed to a different signal type:

```text
Infrastructure failure → learn test/infra reliability      (not regression evidence)
Flaky test              → learn test flakiness              (not regression evidence)
Environment failure     → learn environment reliability     (not regression evidence)
Genuine regression      → learn regression patterns
Production incident     → learn escaped-regression patterns (via Incident correlation)
```

Additional guardrails, unchanged from the prior draft:

* **Correlated-signal double counting** — 500 tests failing from one unavailable dependency collapses to one `INFRASTRUCTURE` signal, not 500 independent regression signals (evidence sharing a `cause_ref` deduplicates).
* **Class imbalance / stale patterns / model drift** — addressed structurally: every `LearningSignal` passes through evaluation (§21) before promotion, rather than updating weights online.
* **Historical-similarity opacity** — a `historically_similar_to` relationship decomposes into component similarities (code pattern, dependency pattern, business flow, failure pattern) rather than exposing one opaque score.
* **Escalation-loop bound** — the `RESIDUAL_RISK → VALIDATION_PLANNING` retry loop (§17) needs a hard iteration cap or cost-based cutoff (tracked as an open decision, §27).

---

## 24. Versioning & Temporal Semantics

The Knowledge Graph changes over time (e.g., `PaymentService → Checkout` in January, migrated to `PaymentServiceV2` by June). Every `Entity` (§4.2), `Relationship`, `Claim`, and `Evidence` object carries temporal validity fields for exactly this reason.

**Invariant:** any assessment, decision, or replay must query the graph *as of* the `graph_snapshot` in its `DecisionContext` (§16) — never the current graph state — when reasoning about a past `Change`. This is what makes §22 (Offline Replay) valid rather than contaminated by hindsight.

Multi-tenancy (`tenant_scope` on every entity, §4.2) is acknowledged here but fully specified in design9.

---

## 25. Implementation Boundaries

This document fixes contracts, not technology or physical storage location. **The Knowledge Graph is the canonical semantic model — it is not necessarily the physical home for every artifact it reasons about:**

```text
Source code       → source repository (referenced, not duplicated, via source_refs[])
CI logs           → artifact/log store
Traces            → telemetry system
Metrics           → metrics system
Incidents         → incident system
Knowledge (relationships, claims) → graph
Evidence references → evidence index (may point into the systems above rather than copy them)
```

This distinction is a major design9 decision and is called out explicitly so the next document doesn't default into "put everything in the graph database."

**Contract-to-component mapping:**
```text
Knowledge Graph      → Graph/storage layer
Claim / Evidence      → Evidence & claims service
ImpactAssessment      → Impact engine
RiskAssessment        → Risk engine
ValidationDecision    → Planning engine
Outcome               → Outcome intelligence
LearningSignal        → Learning engine
DecisionContext       → Reproducibility/versioning service
```

**Explicitly out of scope for this document** (deferred to design9.md):

* Graph database / vector database choice, and which categories of data actually live in the graph vs. adjacent stores
* Messaging technology
* Kubernetes / deployment topology
* LLM provider/model selection
* Microservice boundaries and cloud architecture
* Scaling numbers
* Concrete API endpoint definitions
* Security / tenancy enforcement mechanics (beyond the `tenant_scope` field acknowledged in §4.2)

---

## 26. Frozen Domain Objects

The following are frozen as of this revision. Do not add more conceptual objects unless implementation proves one is necessary:

```text
Entity
Relationship
Claim
Evidence
Change
ImpactAssessment
RiskAssessment
ValidationCandidate
ValidationDecision
Outcome
ResidualRiskAssessment
RiskPolicy
DecisionContext
DecisionAuditRecord
Override
LearningSignal
```

---

## 27. Open Decisions

* Exact default values for `RiskPolicy` thresholds (organization-configurable, but a sane platform default is still needed).
* Hard iteration cap vs. cost-based cutoff for the `RESIDUAL_RISK → VALIDATION_PLANNING` retry loop (§17, §23).
* The precise aggregation function combining `strength × reliability × freshness` into `Claim.confidence` (§6) — left pluggable per §18's algorithm-evolution path.
* How `BusinessFlow` claims get re-validated as production traffic patterns shift over time.
* Multi-tenant access-control model for cross-team evidence sharing (`tenant_scope` acknowledged in §4.2, not designed here).

---

## Summary

The contract chain:
```text
PR → ImpactAssessment → RiskAssessment → ValidationDecision → Outcome → ResidualRiskAssessment → LearningSignal
```
is done when two things are true: an engineer can implement each object above without reinterpreting intent, and given an identical `DecisionContext`, any decision along this chain can be exactly reproduced.

**This document is frozen at the domain-contract level, effective this revision.** Further domain refinement is expected to yield diminishing returns; the unresolved questions from here are physical and runtime, not conceptual. The next document, [design9.md](design9.md) — **System Architecture & Runtime Design** — changes the question from *"what should this platform mean?"* to *"how do we actually build and operate this platform at production scale?"*

**Post-freeze amendment:** an independent architect review of design8/design9 found no blocking issues and confirmed the design is mature enough for implementation. It identified two contract-level gaps, now fixed above: (1) `RiskAssessment` lacked provenance back to the specific `ImpactAssessment`/Claims/Evidence that produced it (§10, `impact_assessment_ref`/`supporting_claim_refs[]`/`supporting_evidence_refs[]` added); (2) `Relationship` and `Claim` risked being implemented as two independent, potentially disagreeing sources of truth (§5, `Relationship` is now explicitly a derived projection with no independently authored temporal or belief state). All other review findings (mid-flight `DecisionContext` staleness, `Outcome.cause_ref` typing, bi-temporal traversal semantics under concurrent ingestion, `estimate()` cold-start, escalation-loop iteration bounds) are deliberately deferred to the vertical-slice implementation, not resolved here — they are implementation questions, not open domain-contract questions.

**The architecture phase is complete:** design1.md–design7.md (conceptual evolution) → design8.md (frozen domain contracts) → design9.md (physical/runtime architecture) → independent architect review → these two targeted corrections → implementation. The next artifact is the vertical slice itself, not another design document.
