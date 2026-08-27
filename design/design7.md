# Architecture Review: From Conceptual to Implementation-Ready

[design6.md](design6.md) established the *why* and the *what*. This document stops adding conceptual recommendations and moves into a concrete architecture review: can the proposed system actually produce trustworthy decisions at scale?

## Assessment

**Architecture-ready, but not yet implementation-ready.** The conceptual model is coherent. The remaining uncertainty is concentrated in a few foundational areas rather than spread across the whole system.

### What Is Now Solid

* Product positioning: clear — change-impact/risk intelligence rather than test selection.
* Core abstraction: Software Change Knowledge Graph.
* Decision chain: Impact → Risk → Evidence → Validation.
* Feedback loop: prediction → validation → outcome → learning.
* AI boundary: AI assists interpretation rather than being the ultimate authority.
* Optimization goal: minimize validation cost while controlling residual risk.
* Explainability: evidence and provenance are first-class.
* Enterprise concerns: policy, auditability, temporal knowledge, and organizational boundaries are recognized.

That's a very good foundation.

---

## The Five Things to Resolve Next

### 1. Define the Knowledge Graph Contract

The next major design artifact. Don't just list entities — define the shape:

```text
Entity
├── identity
├── type
├── version
├── owner
├── metadata
└── lifecycle

Relationship
├── source
├── target
├── relationship_type
├── confidence
├── provenance
├── observed_at
├── valid_from
├── valid_to
└── evidence[]
```

The crucial question: **what is the canonical representation of reality that every agent reads from and writes to?** Until this is defined, the rest of the platform has no stable foundation.

---

### 2. Define the Evidence Contract

The second-most important piece. Make Evidence a proper domain primitive:

```text
Evidence
├── id
├── subject
├── predicate
├── object
├── source
├── source_reference
├── observation
├── strength
├── reliability
├── confidence
├── observed_at
├── valid_until
├── provenance
└── model_version
```

Example:

```text
Subject: PaymentService
Predicate: participates_in
Object: Checkout

Evidence:
  Production traces
  API specification
  Static dependency analysis
  Historical incidents

Confidence: 0.94
```

The graph doesn't merely contain `PaymentService → Checkout`. It contains **`PaymentService → Checkout` because we have these pieces of evidence.** A much more defensible architecture.

---

### 3. Formalize the Risk Engine

The biggest algorithmic gap. Don't prematurely lock into a particular mathematical formula — define the contract first.

The Risk Engine should **consume**:

```text
Impact
Evidence
Historical outcomes
Business criticality
Exposure
Change characteristics
Confidence
```

and **produce**:

```text
RiskAssessment
├── regression_probability
├── business_impact
├── exposure
├── risk_level
├── confidence
├── uncertainty_sources[]
├── evidence[]
├── model_version
└── timestamp
```

This lets different models be experimented with underneath without changing the rest of the platform. **RiskAssessment is a domain contract; the algorithm producing it is replaceable.**

---

### 4. Formalize Validation as an Optimization Problem

Where the architecture becomes genuinely differentiated. The planner shouldn't calculate "test relevance = 90%" — it should evaluate candidate actions against:

```text
Expected risk reduction
Expected information gain
Execution cost
Execution time
Reliability
Coverage
```

Then solve, conceptually:

```text
Minimize:
    validation_cost

Subject to:
    residual_risk <= allowed_threshold
    confidence >= required_threshold
```

Importantly, **the planner should be able to choose "do nothing."** For a low-risk change:

```text
Risk = Low
Confidence = High

→ no additional validation required
```

That's a very important property.

---

### 5. Build the Evaluation Framework Before the Learning System

The biggest practical recommendation. Do not build Continuous Learning first — first build the ability to answer: **"Was the system right?"**

For every historical PR:

```text
Prediction
    ↓
What did we think would happen?

Validation
    ↓
What did we choose to test?

Outcome
    ↓
What actually happened?

Production
    ↓
Did anything escape?

Evaluation
    ↓
How good was the prediction?
```

Then measure:

```text
Impact precision
Impact recall

Risk calibration
Risk discrimination

Regression detection rate
Missed regression rate

Tests executed
Tests avoided

CI time saved
Compute saved

Escaped regression rate
```

Only after that should learning modify the decision process. Otherwise you'll have an AI system that claims to improve without a rigorous mechanism for proving improvement.

---

## Architectural Change: Extend the Domain Chain

design6.md has:

```text
Impact → Risk → Evidence → Validation
```

Extend it to:

```text
                    ┌──────────────┐
                    │    IMPACT    │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │     RISK     │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   EVIDENCE   │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  VALIDATION  │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   OUTCOME    │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ RESIDUAL RISK│
                    └──────┬───────┘
                           │
                           ▼
                        LEARNING
                           │
                           └──────► Knowledge Graph
```

**Why:** Outcome and Residual Risk are essential. The platform isn't finished when tests run — it is finished when it can say: *"Given the evidence we collected, this change now has acceptable residual risk."* That gives the system a concrete stopping condition.

---

## Separate Four Responsibilities

An architectural boundary worth locking down now:

**Knowledge** — What do we know?

```text
Knowledge Graph
Evidence
History
Telemetry
Metadata
```

**Intelligence** — What do we believe?

```text
Impact inference
Risk prediction
Failure classification
Similarity
Root-cause hypotheses
```

**Policy** — What are we required to do?

```text
Risk thresholds
Compliance requirements
Business criticality
Validation requirements
Approval rules
Overrides
```

**Execution** — What action do we actually take?

```text
Tests
E2E
Canary
Deployment
Monitoring
Rollback
```

This separation prevents a common architectural problem where an AI model accidentally becomes both the source of truth and the decision-maker.

---

## Subtle but Critical Principle: Distinguish "Unknown" from "Safe"

```text
Risk: Low
Confidence: 95%
```

means: we have strong evidence this is low risk.

```text
Risk: Low
Confidence: 32%
```

means: we don't know enough to establish that this is low risk.

These must result in different decisions. This principle affects almost every part of the architecture — knowledge graph, evidence, risk, validation, policy, learning — and is one of the things that will make the system substantially more reliable.

---

## The Architecture, Approaching Final Form

```text
                         SOFTWARE CHANGE
                                │
                                ▼
                    ┌───────────────────────┐
                    │ KNOWLEDGE GRAPH       │
                    │                       │
                    │ Code                  │
                    │ Dependencies          │
                    │ APIs / Events         │
                    │ Business Flows        │
                    │ Tests                 │
                    │ History               │
                    │ Production            │
                    └───────────┬───────────┘
                                │
                                ▼
                         ┌────────────┐
                         │   IMPACT   │
                         └─────┬──────┘
                               │
                               ▼
                          ┌──────────┐
                          │   RISK   │
                          └────┬─────┘
                               │
                               ▼
                        ┌─────────────┐
                        │   EVIDENCE  │
                        └──────┬──────┘
                               │
                               ▼
                       ┌──────────────┐
                       │    POLICY    │
                       └──────┬───────┘
                              │
                              ▼
                       ┌──────────────┐
                       │  VALIDATION  │
                       └──────┬───────┘
                              │
                              ▼
                         ┌───────────┐
                         │  OUTCOME  │
                         └─────┬─────┘
                               │
                               ▼
                       ┌──────────────┐
                       │ RESIDUAL RISK│
                       └──────┬───────┘
                              │
                              ▼
                          LEARNING
                              │
                              └──────────► KNOWLEDGE GRAPH
```

---

## Final Recommendation: Freeze the Conceptual Architecture

The next design document should be:

**"Change Intelligence Platform — Domain Contracts & Decision Architecture"**

Containing, concretely:

1. Canonical entity model
2. Graph relationship model
3. Evidence schema + provenance model
4. ImpactAssessment schema
5. RiskAssessment schema
6. ValidationCandidate / ValidationDecision schema
7. Outcome schema
8. ResidualRisk model
9. Policy model
10. Risk/validation algorithms
11. Decision lifecycle/state machine
12. Evaluation methodology
13. Historical replay/offline evaluation
14. Learning update rules
15. Failure and feedback-loop safeguards

After that: system architecture — storage, event flows, ingestion architecture, service boundaries, model serving, graph technology, CI/CD integration, telemetry integration, scalability, and security.

## The Most Important Insight

The design has moved from:

> "How do we intelligently select tests?"

to:

> "How do we continuously acquire evidence about a software change until its residual risk is acceptable?"

That is the conceptual leap that makes the architecture interesting. **Residual Risk should be the final output of the entire system — not test selection.**
