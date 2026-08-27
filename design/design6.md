# From Concepts to Contracts: Schemas, Algorithms, and Measurable Behavior

[design5.md](design5.md) crossed an important boundary: the design is no longer primarily describing a vision — it is beginning to define the operating principles of the platform.

**Main conclusion: do not add more conceptual layers now.** The next iteration should turn the four concepts — Impact, Risk, Evidence, Validation — into explicit contracts, schemas, algorithms, and measurable system behavior. There are still important gaps.

---

## 1. The Architecture Now Has a Real Center

The strongest part is the move toward a **Software Change Knowledge Graph**. That should become the architectural foundation, not merely one component among many:

```text
                         ┌─────────────────────────┐
                         │ Software Change         │
                         │ Knowledge Graph         │
                         │                         │
                         │ Code                    │
                         │ Services                │
                         │ APIs / Events           │
                         │ Data                    │
                         │ Business Capabilities   │
                         │ Business Flows          │
                         │ Tests                   │
                         │ Deployments             │
                         │ Incidents               │
                         │ Production Signals      │
                         └────────────┬────────────┘
                                      │
               ┌──────────────────────┼──────────────────────┐
               │                      │                      │
               ▼                      ▼                      ▼
            Impact                  Risk                  Evidence
               │                      │                      │
               └──────────────────────┼──────────────────────┘
                                      ▼
                              Validation Decision
                                      │
                                      ▼
                                  Execution
                                      │
                                      ▼
                                   Outcome
                                      │
                                      └──────────► Knowledge Graph
```

This is better than thinking of the graph as a database behind the agents — the graph is the platform's persistent memory.

---

## 2. Impact → Risk → Evidence → Validation as First-Class Domain Objects

I'd make these the four first-class domain objects of the product:

* **Impact** — What might this change affect?
* **Risk** — What is the probability and consequence of a bad outcome?
* **Evidence** — What facts support or contradict our belief?
* **Validation** — What action gives us enough additional evidence at the lowest cost?

This gives the system a clean philosophical foundation.

---

## 3. "Evidence" Needs to Be More Rigorous

design5.md has `Evidence / Confidence / Reason`. Add provenance, timestamp/freshness, and evidence strength:

```text
Evidence
├── source
├── observation
├── provenance
├── timestamp
├── freshness
├── reliability
├── strength
└── interpretation
```

Consider these two pieces of evidence:

```text
"Documentation says /checkout calls PaymentService"
```

versus:

```text
"Production traces show /checkout → PaymentService
  in 82.4% of requests over the last 7 days."
```

They shouldn't have equal weight. The platform needs to understand: where did this belief come from, how trustworthy is the source, and how recent is it? This matters more and more as the knowledge graph evolves.

---

## 4. Introduce "Evidence Provenance" Explicitly

Every relationship in the knowledge graph should answer: *why do we believe this relationship exists?*

```text
PaymentService
     │
     └── participates_in → Checkout
                              │
                              └── confidence: 0.93
                                  source:
                                    production_trace
                                  observed:
                                    2026-08-20
                                  evidence:
                                    1.8M requests
```

versus a weaker inferred relationship:

```text
PaymentService
     │
     └── participates_in → SubscriptionRenewal
                              │
                              └── confidence: 0.61
                                  source:
                                    LLM inference
                                  evidence:
                                    API documentation
                                    test names
```

This makes the graph itself uncertainty-aware.

---

## 5. Risk Should Become a Formal Decision Model

design5.md correctly rejects `Risk = Probability × Impact × Uncertainty`, but `Decision = Risk + Confidence + Validation Cost` is still a conceptual statement, not a model. Eventually:

```text
Risk:
    probability
    impact
    exposure

Confidence:
    impact_confidence
    probability_confidence
    evidence_quality

Validation:
    cost
    duration
    coverage
    expected_information_gain
```

Then the planner can reason:

```text
                 ┌──────────────┐
                 │ Candidate    │
                 │ Validation A │
                 └──────┬───────┘
                        │
              Expected Risk Reduction
                        │
              Expected Execution Cost
                        │
                        ▼
                  Value of Evidence
```

Leading to a much more interesting optimization problem: **which validation action gives us the greatest reduction in residual risk per unit of cost?** — more powerful than simply ranking tests.

---

## 6. "Residual Risk" Is Potentially the Most Important Concept Added So Far

I'd promote this even further. The system's real job isn't "select tests" — it's **reduce residual risk to an acceptable threshold**.

```text
Initial assessment

Probability: 0.35
Impact: Critical
Residual risk: HIGH
```

Run targeted integration tests:

```text
Evidence:
  24 tests passed
  3 relevant paths exercised

Updated probability: 0.08
Confidence: 0.94
Residual risk: LOW
```

Then decide:

```text
LOW residual risk  → approve validation
HIGH residual risk → run additional validation
```

This creates a natural stopping condition.

---

## 7. Need a Formal "Decision Policy"

Still missing. Given `Risk: High, Confidence: 72%` — what exactly happens? Need policy such as:

```text
IF
    business_impact = critical
AND
    residual_risk > threshold
THEN
    require E2E + canary
```

or:

```text
IF
    risk = medium
AND
    confidence < 70%
THEN
    expand impact analysis
```

The architecture should distinguish **Intelligence** ("what do we believe?") from **Policy** ("what are we allowed/required to do?"). Important for enterprise environments.

---

## 8. Risk Policy Should Be Organization-Configurable

Different companies — and different domains within one company — have different risk tolerance. Payment/Authentication/Billing may need dramatically different thresholds than an internal dashboard or developer tooling.

```text
Risk Policy
├── business criticality
├── risk thresholds
├── confidence thresholds
├── validation requirements
├── deployment requirements
└── override rules
```

The intelligence engine provides the assessment; the policy engine determines the required action.

---

## 9. Test Selection as Information Acquisition Under a Cost Constraint

A strong formulation. Each test can have:

```text
Test
├── execution_cost
├── execution_time
├── impacted_entities
├── historical_detection_rate
├── flakiness
├── business_flow_coverage
└── expected_risk_reduction
```

The planner isn't asking "which tests are related?" — it's asking **"which tests provide the most useful evidence about the risks we currently care about?"**

---

## 10. Model Negative Evidence Explicitly

The platform shouldn't only store "Test A supports Checkout." It should also learn "Test A provides almost no evidence about this particular risk."

```text
Test: UserLoginE2E

Relevant to:
  Authentication: HIGH
  Checkout: LOW
  Payment authorization: NONE
```

Otherwise historical test associations can cause test suites to grow unnecessarily. The planner needs to understand incremental information value.

---

## 11. Failure Intelligence Should Become "Outcome Intelligence"

A test failure is only one kind of outcome. The platform cares about:

```text
Test failure
Test pass
Deployment failure
Canary degradation
Production anomaly
Customer incident
No observed issue
```

Conceptual model:

```text
Validation
     ↓
Outcome
     ↓
Evidence Update
     ↓
Risk Update
```

Failure Intelligence becomes one specialization of Outcome Intelligence — also making the architecture naturally compatible with canaries and production monitoring.

---

## 12. The Learning Loop Needs Guardrails

Avoid:

```text
Failure
 ↓
AI learns pattern
 ↓
Run more tests
 ↓
More tests fail
 ↓
AI learns even more
 ↓
Run even more tests
```

This feedback loop can make the system increasingly conservative. Need mechanisms for:

* avoiding feedback amplification
* handling class imbalance
* distinguishing flaky tests
* detecting stale historical patterns
* measuring model drift
* avoiding duplicated evidence
* preventing correlated signals from being counted multiple times

For example, 500 tests failing because one service was unavailable should not become 500 independent pieces of regression evidence.

---

## 13. Historical Similarity Needs Careful Treatment

`PR-123 historically_similar_to PR-871` is valuable, but "similar" should be explainable:

```text
Code structure similarity
+
Dependency similarity
+
Business-flow similarity
+
Change-type similarity
+
Failure-mode similarity
```

Ideally:

```text
Similarity = 0.87

Because:
  code pattern:       0.91
  dependency pattern: 0.82
  business flow:      0.95
  failure pattern:    0.77
```

Otherwise historical learning becomes another opaque AI subsystem.

---

## 14. Missing: Versioning / Temporal Knowledge

The knowledge graph changes over time:

```text
January:
PaymentService → Checkout

June:
Checkout migrated to PaymentServiceV2
```

Historical decisions must still be evaluated against the graph as it existed at that time. Relationships need validity windows:

```text
relationship
valid_from
valid_to
observed_at
source_version
```

Especially important for learning — otherwise the system could incorrectly use today's architecture to explain yesterday's incident.

---

## 15. Missing: Multi-Tenancy / Organizational Boundaries

If this is a platform rather than a single-repository tool, eventually define:

```text
Organization
Team
Repository
Environment
Service ownership
Access boundaries
```

Particularly because production telemetry, incidents, business KPIs, and code can have different permissions. Doesn't need deep design yet, but the architecture should acknowledge the boundary.

---

## 16. Four Planes for the Implementation Architecture

**Knowledge Plane** — Knowledge Graph, Evidence Store, Historical Outcomes, Metadata

**Intelligence Plane** — Impact Analysis, Risk Prediction, Failure Analysis, Pattern Discovery

**Decision Plane** — Policy, Validation Optimization, Risk Thresholds, Approval Gates

**Execution Plane** — Test Runner, CI/CD, Canary, Monitoring, Deployment

```text
                    ┌─────────────────────┐
                    │   KNOWLEDGE PLANE   │
                    │ Graph + Evidence    │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ INTELLIGENCE PLANE  │
                    │ Impact + Risk       │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │    DECISION PLANE   │
                    │ Policy + Planning   │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   EXECUTION PLANE   │
                    │ Tests + Canary      │
                    └──────────┬──────────┘
                               │
                               ▼
                           Outcomes
                               │
                               └──────► Knowledge Plane
```

A natural next evolution of the architecture.

---

## 17. What NOT to Add Right Now

* more AI agents
* more graph types
* more sophisticated LLM orchestration
* autonomous coding
* automatic remediation
* elaborate microservice decomposition

These are distractions. The conceptual architecture is already rich enough — the next challenge is making the existing concepts precise.

---

## 18. The Next Design Document Should Contain Concrete Schemas

```text
ImpactAssessment
├── change_id
├── affected_entities[]
├── impact_type
├── probability
├── confidence
├── evidence[]
├── created_at
└── model_version
```

```text
Evidence
├── evidence_id
├── source_type
├── source_reference
├── observation
├── strength
├── reliability
├── observed_at
├── valid_until
└── provenance
```

```text
ValidationDecision
├── change_id
├── risk_before
├── target_residual_risk
├── candidate_validations[]
├── selected_validations[]
├── estimated_cost
├── expected_risk_reduction
├── decision_reason
└── policy_version
```

```text
Outcome
├── validation_id
├── result
├── failure_class
├── root_cause
├── production_correlation
├── actual_impact
└── learning_signal
```

At that point, the architecture becomes implementable.

---

## 19. Upgraded Success Metrics

**Accuracy** — Impact precision/recall, Risk calibration, Root-cause accuracy, Historical-pattern accuracy

**Effectiveness** — Regression detection rate, Missed-regression rate, Residual-risk accuracy

**Efficiency** — Tests avoided, CI time saved, Compute cost saved, Mean validation time

**Trust** — Explainability coverage, Decision override rate, False-positive rate, Engineer acceptance rate

The critical metric isn't "how many tests did we skip?" It is:

> How much validation cost did we remove without materially increasing escaped regression risk?

That should probably become one of the platform's north-star metrics.

---

## 20. Recommended Final Architecture

```text
                         ┌─────────────────────────┐
                         │ SOFTWARE CHANGE         │
                         │ KNOWLEDGE GRAPH         │
                         │                         │
                         │ Code                    │
                         │ APIs / Events           │
                         │ Business Flows          │
                         │ Tests                   │
                         │ Incidents               │
                         │ Deployments             │
                         │ Production              │
                         └────────────┬────────────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │    IMPACT     │
                              │               │
                              │ What changed? │
                              │ What is       │
                              │ affected?     │
                              └───────┬───────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │     RISK      │
                              │               │
                              │ Probability   │
                              │ Impact        │
                              │ Exposure      │
                              │ Confidence    │
                              └───────┬───────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │   EVIDENCE    │
                              │               │
                              │ History       │
                              │ Tests         │
                              │ Telemetry     │
                              │ Traces        │
                              │ Incidents     │
                              └───────┬───────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │  VALIDATION   │
                              │               │
                              │ Tests         │
                              │ E2E           │
                              │ Canary        │
                              │ Monitoring    │
                              └───────┬───────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │    OUTCOME    │
                              │               │
                              │ Passed        │
                              │ Failed        │
                              │ Incident      │
                              │ Production    │
                              └───────┬───────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │    LEARNING   │
                              └───────┬───────┘
                                      │
                                      └──────────► Knowledge Graph
```

---

## Bottom Line

The design is now architecturally compelling. The evolution across design1.md–design6.md:

```text
Test Selection
      ↓
Risk-Based Test Selection
      ↓
Change-Impact Intelligence
      ↓
Evidence-Based Risk Management
      ↓
Adaptive Validation
```

That's the right trajectory. The next document should stop being primarily conceptual and become a **technical contract**, answering with schemas and examples:

1. What exactly are the entities and relationships in the knowledge graph?
2. What exactly is an evidence object, and how is provenance/confidence represented?
3. How exactly is risk calculated and calibrated?
4. How does the planner calculate the expected value/cost of a validation action?
5. How does validation update residual risk?
6. How are prediction and actual outcome stored and compared?
7. How does learning change future decisions without creating feedback bias?
8. How do you evaluate the system offline before allowing it to control production CI/CD?

If those are nailed down, the architecture is implementation-ready at the domain/design level. The remaining work becomes engineering choices — storage technology, eventing, service boundaries, model infrastructure, CI integrations, deployment architecture — rather than fundamental uncertainty about what the platform is supposed to do.
