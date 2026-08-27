# Vertical Slice — First Implementation Milestone

This is the first real implementation of the design8/design9 decision chain, scoped exactly as directed: one repository, no production/incident/organizational access, one real change, taken all the way through to a validated, explainable decision.

```
Repository / PR
      ↓
Understand the change
      ↓
Determine potential impact
      ↓
Assess risk
      ↓
Determine appropriate validation
      ↓
Run one real validation
      ↓
Record the outcome
      ↓
Produce an explainable decision
```

## What's here

- [`analyze_change.py`](analyze_change.py) — the analyzer. Given a git repository and a ref to diff against, it produces a `Change`, `ImpactAssessment`, `RiskAssessment`, `ValidationDecision`, executes the recommended validation for real, records the `Outcome`, and renders a business-facing report plus a JSON audit record.
- [`reports/verify-cache-change-report.md`](reports/verify-cache-change-report.md) — the actual output for the demonstration change (see below).
- [`reports/verify-cache-change-report.audit.json`](reports/verify-cache-change-report.audit.json) — the structured record backing that report.
- [`reports/vertical-slice-package.md`](reports/vertical-slice-package.md) — the business-readable package (evidence available vs. missing, limitations, next-value opportunities) requested alongside the report.

## The demonstration change

Target repository: [social-media-mini](https://github.com/venusabhay/social-media-mini), cloned locally to `/Users/abhay/git-venusabhay/social-media-mini` (the canonical local location for this repo) — nothing was pushed back to it. A real, plausible code change was made to `services/auth-service/server.js`: the `/verify` endpoint (called by `post-service` and `user-service` on every authenticated request) was given a 5-second in-memory cache to reduce database load. This is exactly the kind of change the design was built to reason about: small, and touching a structurally central, security-adjacent path.

## How to reproduce

```bash
python3 analyze_change.py <path-to-repo> \
  --against HEAD \
  --node-bin <directory containing a working node/npm> \
  --out reports/some-report.md
```

The tool only reads the target repository and runs its own existing `npm test` — it never modifies, commits, or pushes anything there.

## Deliberate simplifications vs. the frozen design

Per instruction, the architecture (design8.md / design9.md) was not reopened. Where it leaves an implementation choice open, the smallest reasonable choice was made here, and is listed explicitly rather than silently substituted:

| Design8/9 concept | What this slice actually does |
| --- | --- |
| Knowledge Graph, Evidence index, decision store | None of these exist. Every object is a plain in-memory structure for the duration of one run, serialized to a JSON audit file. There is no persistence across runs, no multi-hop graph traversal, and no historical corpus. |
| `Claim` with a versioned aggregation function | Not implemented. Each piece of evidence is surfaced directly in the report; confidence is a qualitative bucket (HIGH/MEDIUM/LOW) assigned by an explicit rule in `analyze_change.py`, never a numeric score presented as precise. |
| `RiskAssessment.probability` / `business_impact` as calibrated values | Qualitative buckets from explicit, inspectable rules (structural fan-in, sensitive-path-name match, newly-introduced-state patterns in the diff). Not calibrated against historical outcomes — there is no history yet. |
| `DecisionContext` | Approximated by recording the repo path, git ref/HEAD, and generation timestamp in the audit JSON. Sufficient to say what a decision was based on; not a general reproducibility service. |
| `RiskPolicy` | A single hardcoded threshold function (`final_recommendation()`), not a configurable, versioned object. There is exactly one policy and one organization in this slice. |
| `Override` | Not implemented — there is no running system to override yet; a human reads the report and decides. |
| `LearningSignal` / Continuous Learning | Not implemented — this slice produces one decision, it does not yet learn from outcomes across changes. |

None of these are architectural contradictions — they are exactly the kind of implementation-scoping decisions design8 §18 anticipated ("rules today" as the first point on the evolution path) and design9 explicitly deferred until there's a real slice to learn from.

## What this slice actually found

The most significant finding wasn't about the demonstration change's caching logic — it was that **none of the three backend services' test files import their own `server.js`**; each hand-duplicates its own route logic for testing. The analyzer detected this generically (it checks whether the test file covering a changed route imports the changed module) and used it to downgrade confidence and drive the final recommendation to `REQUIRE_ADDITIONAL_VALIDATION` even though the existing tests passed. See [vertical-slice-package.md](reports/vertical-slice-package.md) for the full writeup.

## Relationship to the rest of the repository

- [`../design/business-vision.md`](../design/business-vision.md) — the business framing this slice is meant to provide first evidence for.
- [`../design/design8.md`](../design/design8.md), [`../design/design9.md`](../design/design9.md) — the frozen domain contracts and architecture this slice implements a deliberately narrow slice of.
