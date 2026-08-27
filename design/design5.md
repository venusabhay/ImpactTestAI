# Toward Implementation-Ready: Data, Evidence, Decision, and Evaluation Models

[design4.md](design4.md) got the conceptual framing right — a change-impact and risk-intelligence platform, not merely AI-powered test selection. This document assesses where that design still falls short of implementation-ready, and defines what's missing underneath it.

## Assessment

| Dimension | Assessment |
| --- | --- |
| Product vision | Excellent |
| Architectural direction | Very strong |
| Differentiation | Strong |
| End-to-end story | Strong |
| Explainability | Strong |
| Learning loop | Strong conceptually |
| Data/model definition | Needs more detail |
| Risk methodology | Needs more detail |
| Operational architecture | Needs more detail |
| Evaluation/accuracy strategy | Major missing piece |

The most important next step is not adding more agents. It is defining the **data model, evidence model, decision model, and evaluation model** underneath the architecture.

---

## 1. The Unified Impact Model Is Now Clearly the Center

design4.md's biggest improvement was establishing:

```text
                    ┌────────────────────────┐
                    │   UNIFIED IMPACT MODEL  │
                    │                        │
                    │ Code                   │
                    │ Services               │
                    │ APIs / Events          │
                    │ Data                  │
                    │ Business Capabilities │
                    │ Business Flows        │
                    │ Tests                 │
                    │ Incidents             │
                    │ Production Signals    │
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │ Decision Intelligence  │
                    └────────────────────────┘
```

That's the correct mental model — but the name should go further. Don't call it just an "Impact Model." Define it as a **Software Change Knowledge Graph** (or Change Impact Knowledge Model), because it isn't simply storing impact — it represents relationships between entities:

```text
PR-123
  │
  ├── changes → PaymentService.authorize()
  │
  ├── affects → POST /payments
  │
  ├── publishes → PaymentAuthorized
  │
  ├── participates_in → Checkout
  │
  ├── affects → Payment Success KPI
  │
  ├── covered_by → PaymentIntegrationTest
  │
  └── historically_similar_to → PR-871
```

That distinction matters when designing storage and querying.

---

## 2. Define the Canonical Entities

Probably the single biggest missing section. The design should explicitly define the entities the platform understands:

```text
Repository
Repository Version
Commit
Pull Request
File
Symbol
Function
Class
Service
API
Event
Message
Database
Schema
Feature Flag
Business Capability
Business Flow
Business Operation
Test
Test Suite
Deployment
Incident
Failure
Production Signal
Owner
```

And the relationships between them:

```text
Function ──calls──> Function
Service ──exposes──> API
Service ──publishes──> Event
Event ──consumed_by──> Service
API ──used_by──> Business Flow
Business Flow ──validated_by──> Test
Test ──failed_with──> Failure
Failure ──correlated_with──> Incident
Change ──affected──> Business Capability
```

**Why this matters:** Without a canonical entity model, different agents may develop different interpretations of "service", "flow", "impact", "dependency", "failure", etc. That eventually creates inconsistent decisions.

---

## 3. Risk Needs One More Layer: Evidence

design4.md's formulation — `Probability × Impact × Uncertainty` — is directionally good, but uncertainty should not literally be multiplied into risk. Uncertainty isn't the same thing as risk.

For example:

```text
Regression probability = 5%
Business impact = Critical
Confidence = 30%
```

This doesn't mean the regression risk is "30% × something." It means: *"We believe the risk may be low, but we don't know enough to trust that conclusion."* That's a different state.

Model it instead as:

```text
Risk
├── Probability
├── Impact
├── Exposure
└── Confidence
```

Then:

```text
Decision
   =
Risk
+
Confidence
+
Validation Cost
```

This enables a much more robust behavior:

```text
High risk + high confidence
→ targeted aggressive validation

High risk + low confidence
→ broaden analysis + validation

Low risk + high confidence
→ minimal validation

Low risk + low confidence
→ investigate before optimizing
```

---

## 4. Add an Explicit Evidence Model

Every conclusion should have evidence attached to it. For example:

```text
Impact: Checkout
Evidence:
  - Changed PaymentService.authorize()
  - Called by POST /checkout
  - /checkout belongs to Checkout Flow
  - 3 historical regressions involved similar changes
  - 82% of production checkout traffic reaches this path
Confidence: 0.91
```

The risk engine isn't simply saying "Risk = 87." It is saying "Risk is high because of these observable facts." This is extremely important for enterprise adoption.

---

## 5. Distinguish Prediction from Outcome in the Learning Loop

Store both:

**Prediction**

```text
PR-123
Predicted:
  affected flow = Checkout
  regression probability = 0.22
  risk = High
  selected tests = 17
```

**Outcome**

```text
Observed:
  1 test failed
  root cause = genuine regression
  affected flow = Checkout
  production incident = Yes
  customer impact = Payment failures
```

Measuring Prediction → Outcome over time turns the learning engine into something scientifically measurable rather than simply "AI learns from history."

---

## 6. Add an Evaluation Framework

The largest omission in design4.md. How will you know the system is actually getting better? You need explicit platform metrics:

**Impact accuracy** — of the business capabilities predicted to be affected, how many were actually affected?

**Risk calibration** — if the system says "20% regression probability," then across many similar predictions, approximately 20% should actually regress.

**Test-selection effectiveness** — measure:

```text
Regression detection rate
──────────────────────────
Tests executed
```

versus the baseline:

```text
Full suite detection rate
──────────────────────────
Full suite execution
```

**Efficiency** — measure tests avoided, execution time saved, compute cost saved, regression detection retained.

The ideal result is: **90%+ of meaningful regressions detected with 20% of the test execution cost.** The exact target is TBD, but the principle needs to be explicit.

---

## 7. Add a "Decision Audit Trail"

Make this a first-class concept. For every PR:

```text
PR
 ↓
Impact Analysis
 ↓
Risk Decision
 ↓
Validation Decision
 ↓
Execution
 ↓
Failure Analysis
 ↓
Learning Update
```

Store the decisions. Then engineers can ask:

* Why did the platform select these tests?
* Why didn't it select this test?
* Why was this PR classified as high risk?
* What historical incidents influenced the decision?
* What did the platform believe before execution?
* Was that belief correct?

This turns the system into an auditable decision engine.

---

## 8. The Architecture Is Still Slightly Too Linear

design4.md correctly says "this should be a persistent intelligence loop," but the diagram still visually looks mostly like a chain:

```text
Impact → Risk → Validation → Execution → Failure → Learning → Impact
```

It should explicitly show that all components read from and write evidence to the knowledge model:

```text
                         ┌────────────────────────┐
                         │ CHANGE INTELLIGENCE    │
                         │ KNOWLEDGE MODEL        │
                         │                        │
                         │ Code                   │
                         │ APIs / Events          │
                         │ Business Flows         │
                         │ Tests                  │
                         │ Incidents              │
                         │ Production             │
                         └───────┬───────┬────────┘
                                 │       │
                  ┌──────────────┘       └──────────────┐
                  ▼                                     ▼
             Impact Analysis                         History
                  │                                     │
                  └──────────────┬──────────────────────┘
                                 ▼
                         Risk + Confidence
                                 │
                                 ▼
                       Validation Planning
                                 │
                                 ▼
                            Execution
                                 │
                                 ▼
                       Failure Intelligence
                                 │
                                 ▼
                          Outcome Evidence
                                 │
                                 └──────────────► Knowledge Model
```

This better represents the architecture described in prose.

---

## 9. AI Reasoning Should Not Be the Final Authority

design4.md's separation between deterministic and AI reasoning is excellent. Strengthen it further: **AI proposes interpretations; evidence and deterministic systems constrain decisions.**

For example, the LLM might infer "this API appears to represent checkout." The system should validate that inference using API traffic, service metadata, traces, existing tests, documentation, ownership, and historical deployments.

Conceptually:

```text
AI inference
     ↓
Evidence retrieval
     ↓
Validation
     ↓
Confidence
     ↓
Decision
```

rather than:

```text
AI inference
     ↓
Decision
```

---

## 10. Production Telemetry Needs to Become a Real Input, Not Just a Learning Source

design4.md mentions production telemetry inside Continuous Learning, which is good — but it should be part of the core model:

```text
                         Change
                           ↓
                      Prediction
                           ↓
                         Tests
                           ↓
                       Deployment
                           ↓
                 Production Telemetry
                           ↓
                    Actual Outcome
                           ↓
                        Learning
```

The platform should be able to learn: *"Our tests predicted this change was safe, but production behavior says otherwise."* That is vastly more valuable than learning only from CI failures.

---

## 11. Keep "Minimum Validation" — Make It Rigorous

design4.md's minimum-validation concept is excellent and should be kept. It gives a precise optimization objective:

> Minimize validation cost subject to acceptable residual risk.

Expressed at a high level:

```text
Minimize:
    Validation Cost
Subject to:
    Residual Risk ≤ Risk Threshold
    Confidence ≥ Required Confidence
```

This gives the Validation Planner a precise reason for existing.

---

## 12. Add "Residual Risk"

Before validation:

```text
Risk = High
```

After running selected tests:

```text
Risk before validation: High
Validation evidence: Strong
Residual risk: Low
```

This gives the platform a clear purpose: it isn't simply choosing tests, it is **reducing uncertainty/risk through evidence**. The loop becomes:

```text
Initial Risk
     ↓
Choose Evidence
     ↓
Collect Evidence
     ↓
Update Risk
     ↓
Residual Risk
```

That is a much stronger theoretical foundation.

---

## 13. The Final Conceptual Model

Four fundamental concepts, with everything else supporting them:

1. **Impact** — What could this change affect?
2. **Risk** — How likely and consequential is a regression?
3. **Evidence** — What do we know, and how confident are we?
4. **Validation** — What is the cheapest way to reduce residual risk to an acceptable level?

```text
                 CODE CHANGE
                      │
                      ▼
               ┌─────────────┐
               │   IMPACT    │
               │ What changed│
               │ What breaks?│
               └──────┬──────┘
                      ▼
               ┌─────────────┐
               │    RISK     │
               │ Probability │
               │ × Impact    │
               └──────┬──────┘
                      ▼
               ┌─────────────┐
               │   EVIDENCE  │
               │ History     │
               │ Confidence  │
               │ Telemetry   │
               └──────┬──────┘
                      ▼
               ┌─────────────┐
               │ VALIDATION  │
               │ Minimum cost│
               │ Maximum info│
               └──────┬──────┘
                      ▼
                    RESULT
                      │
                      ▼
              ┌───────────────┐
              │ RESIDUAL RISK │
              └───────┬───────┘
                      │
                      ▼
                  LEARNING
                      │
                      └──────► Knowledge Model
```

---

## What to Add Before Calling This Design "Complete"

Not many more components. Instead, five concrete design sections:

1. **Canonical Entity & Relationship Model** — define exactly what exists in the Unified Impact Model.
2. **Evidence & Confidence Model** — define how every inference gets evidence, confidence, provenance, and freshness.
3. **Risk & Decision Model** — define probability, impact, confidence, thresholds, and residual risk.
4. **Validation Optimization Model** — define how the planner trades off regression coverage, execution time, cost, and confidence.
5. **Evaluation & Learning Model** — define how to measure whether predictions, risk scores, test selection, failure diagnosis, and learning are actually improving.

## Strongest Recommendation

Don't spend the next iteration expanding the list of agents — there are already enough conceptual components. The next design iteration should answer:

> What is the data flowing through this system, what evidence supports every decision, how is each decision evaluated against reality, and how does that evidence update the model?

If those four questions can be answered rigorously, the architecture moves from a very good conceptual vision to something an engineering team can actually design and implement — and, importantly, something whose intelligence can be objectively measured rather than simply claimed.
