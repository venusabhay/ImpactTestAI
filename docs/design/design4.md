# Reframing: A Change-Impact & Risk-Intelligence Platform

This is a **change-impact and risk-intelligence platform**, not merely an AI-powered test-selection system. This document reframes [design2.md](design2.md) / [design3.md](design3.md) around that distinction.

## 1. Clear System Objective

> Given a code change, determine what technical and business capabilities may be affected, estimate regression risk and uncertainty, select the minimum validation required to achieve sufficient confidence, analyze failures, and continuously improve future decisions using historical and production evidence.

This gives every component a clear purpose.

---

## 2. A Unified Impact Model

The most important addition. Instead of treating the Code Graph, API Graph, Business Flow Graph, tests, incidents, and historical data as independent systems, define a common model connecting them:

```text
Code
 ↓
Service / Component
 ↓
API / Event / Data Contract
 ↓
Business Capability
 ↓
Business Flow
 ↓
Tests
 ↓
Failures / Incidents
 ↓
Production Impact
```

Every stage should be able to reference the same entities.

**Why:** Without this, the architecture risks becoming a chain of loosely connected agents. With it, the platform develops a persistent understanding of the software system.

---

## 3. Risk = Probability × Impact × Uncertainty

The Risk Engine should not just output an arbitrary score. It should answer:

```text
How likely is a regression?
How severe would it be?
How confident are we in our analysis?
What evidence supports the decision?
```

Example:

```text
Regression probability: 18%
Business impact: Critical
Confidence: 86%
Historical evidence: Strong
Overall risk: High
```

**Why:** This makes risk explainable, measurable, and actionable.

---

## 4. Historical Learning as an Evidence System

The learning engine should learn from more than test failures. It should connect:

```text
Code Change
   ↓
Predicted Impact
   ↓
Selected Tests
   ↓
Test Results
   ↓
Root Cause
   ↓
Deployment
   ↓
Production Behavior
   ↓
Actual Incident / Customer Impact
```

And distinguish:

* genuine regression
* flaky test
* infrastructure failure
* environment failure
* pre-existing failure
* test-data issue
* actual production incident

**Why:** Otherwise the system can learn incorrect patterns and progressively make worse decisions.

---

## 5. Optimal Validation, Not Just Test Selection

Broaden the concept from "Which tests should we run?" to **"What is the minimum validation required for this change?"**

```text
Low risk
→ Unit tests

Medium risk
→ Targeted integration tests

High risk
→ Integration + E2E

Critical risk
→ Tests + canary + enhanced monitoring
```

**Why:** The best validation strategy isn't always "run more tests." Sometimes deployment strategy, monitoring, or canarying provides better evidence.

---

## 6. Confidence and Explainability at Every Stage

Every intelligent decision should have:

```text
Decision
Confidence
Evidence
Reason
```

Example:

> Payment service was selected because the PR modifies authorization logic, which is called by `/checkout`, which participates in the checkout business flow, and three historically similar changes caused payment regressions.

**Why:** Engineering teams need to trust and challenge the system. Black-box risk scores will be difficult to adopt.

---

## 7. Handle Modern Architectural Dependencies

The dependency model shouldn't stop at function → API. It should eventually understand:

* synchronous APIs
* asynchronous events
* queues
* database/schema changes
* feature flags
* configuration
* scheduled jobs
* external services
* infrastructure dependencies

**Why:** A business flow can cross service boundaries without an API call. Otherwise the impact graph will have blind spots.

---

## 8. Separate Deterministic Analysis from AI Reasoning

**Deterministic:**

```text
Static dependencies
API relationships
Test-to-code mapping
Execution results
Historical statistics
Tracing relationships
```

**AI/ML-assisted:**

```text
Business-flow inference
Business-impact interpretation
Failure classification
Root-cause hypotheses
Risk prediction
Historical pattern discovery
```

**Why:** You want AI where semantic reasoning is valuable, not where conventional analysis is more reliable.

---

## The Architecture

```text
                         CODE CHANGE
                              │
                              ▼
                  ┌─────────────────────┐
                  │ Unified Impact Model│
                  │                     │
                  │ Code                │
                  │ APIs / Events       │
                  │ Data                │
                  │ Business Flows      │
                  │ Tests               │
                  │ Incidents           │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │ Risk + Uncertainty  │
                  │                     │
                  │ Probability         │
                  │ Business Impact     │
                  │ Historical Evidence │
                  │ Confidence          │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │ Validation Planner   │
                  │                     │
                  │ Tests               │
                  │ E2E                 │
                  │ Canary              │
                  │ Monitoring          │
                  └──────────┬──────────┘
                             │
                             ▼
                         EXECUTION
                             │
                             ▼
                  ┌─────────────────────┐
                  │ Failure Intelligence│
                  │                     │
                  │ Classification      │
                  │ Root Cause          │
                  │ Regression Evidence │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │ Continuous Learning │
                  │                     │
                  │ Tests               │
                  │ Incidents           │
                  │ Deployments         │
                  │ Production Telemetry│
                  └──────────┬──────────┘
                             │
                             └──────────► IMPACT MODEL
```

---

## Why This Is the Right Final Framing

The strongest idea in design2.md / design3.md is the progressive expansion of context:

```text
code → technical → API → business → risk → history → validation → failure → learning
```

That should be preserved. But the architectural interpretation should change from a **linear pipeline** to a **persistent intelligence loop**.

* The pipeline is how a single PR is processed.
* The Unified Impact Model + Learning Loop is what makes the platform increasingly intelligent across thousands of PRs.

That distinction is critical.

## In One Sentence

> Build a continuously learning software-impact graph that understands how code changes propagate into business risk, then use that understanding to select the cheapest validation strategy that provides sufficient confidence.

If the design can convincingly implement that sentence, it has a much stronger architectural story than simply "AI agents for intelligent test selection."
