# Condensed Pipeline View

A single linear distillation of the [design2.md](design2.md) architecture — useful as the one-diagram summary of what the platform does end to end.

```text
Code Change
    ↓
Technical Dependencies
    ↓
API Dependencies
    ↓
Business Flows
    ↓
Business Impact
    ↓
Risk
    ↓
Historical Regression Patterns
    ↓
Optimal Test Selection
    ↓
Test Execution
    ↓
Failure Intelligence
    ↓
Continuous Learning
```

## Stage Mapping

| Stage | Corresponding Component (design2.md) |
| --- | --- |
| Code Change | PR Analysis Agent |
| Technical Dependencies | Code Dependency Graph |
| API Dependencies | API Dependency Graph |
| Business Flows | Business Flow Graph |
| Business Impact | Business Impact Analysis Agent |
| Risk | Risk Analysis Engine |
| Historical Regression Patterns | Historical Learning Engine |
| Optimal Test Selection | Test Planning Agent + Coverage Planner |
| Test Execution | Test Execution Agent |
| Failure Intelligence | Failure Intelligence Agent |
| Continuous Learning | Continuous Learning Engine |

## Why This View Matters

Each arrow is a widening of context, not just a handoff:

* **Code Change → Technical Dependencies**: from "what lines changed" to "what else in the codebase touches this."
* **Technical Dependencies → API Dependencies**: from internal call graph to externally exposed contracts.
* **API Dependencies → Business Flows**: from endpoints to the user journeys that chain them together.
* **Business Flows → Business Impact**: from "what could break" to "what a stakeholder would care about."
* **Business Impact → Risk**: impact gets weighted by criticality (payment, auth, etc.) into a score.
* **Risk → Historical Regression Patterns**: past incidents adjust the score — components with a track record of breaking get extra scrutiny.
* **Historical Regression Patterns → Optimal Test Selection**: risk plus history decides which tests actually need to run, not the full suite.
* **Optimal Test Selection → Test Execution → Failure Intelligence**: selected tests run, and failures are diagnosed with root cause, not just pass/fail.
* **Failure Intelligence → Continuous Learning**: every result feeds back so the next PR's risk scoring and test selection are sharper.

This is the loop that makes the platform compound in value over time rather than staying a static test runner.
