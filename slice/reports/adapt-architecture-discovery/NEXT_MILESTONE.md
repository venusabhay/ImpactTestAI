# Next Milestone — Scope Decision (Business Checkpoint After v6)

Recorded after review of the v6 held-out results. **No implementation work has started on this.** This document defines scope for whenever the business owner greenlights it — it is not itself the greenlight.

## Business recommendation

**Continue the experiment. Do not deploy `ADAPT_ARCHITECTURE_DISCOVERY` as a trusted engineering gate yet.**

Justification: the core idea generalized to a genuinely unseen repository (`expressjs/express`, 2/2 real changes correctly and precisely analyzed) — that's real evidence the approach is more than a fit to the two repositories it was built against. But two new, real gaps surfaced in the same round on a different unseen repository. The open question isn't "does this work" (it demonstrably can) — it's whether continued improvement makes the mechanism more general, or turns it into an accumulating pile of exceptions. That's not yet answered, and it's the thing the next held-out round needs to answer.

## North-star test for the next round

> Can this understand new repositories from their architecture, or are we gradually teaching it every repository one at a time?

Every future held-out round should be read against this question specifically, not just against a pass/fail count.

## Next engineering milestone (narrowly scoped, not yet started)

**Improve generic JavaScript/TypeScript source discovery so that route detection ignores comments and controller-method dependencies can be traced using repository evidence, without introducing repository-specific rules.**

Concretely, this is exactly the two v6 findings — no more, no less:

1. **Comment-awareness in route/export scanning.** The regex scanner currently matches code-shaped text inside `//` and presumably `/* */` comments as if it were real code (demonstrated directly in v6: a route-registration example inside a comment was matched as a genuine route). Fix must be general (e.g., strip or mask comment spans before scanning) — not a check for any specific comment wording or file.
2. **Controller-method dependency tracing.** `router.get(path, controller.methodName)` (a property-access reference, common in class-based controllers) is not connected back to `controller`'s definition today, because export discovery only recognizes `export const`/`export function`, and middleware-argument extraction stores the full dotted reference rather than resolving it. Fix must use general repository evidence (e.g., resolve `controller` to its import, find `methodName` as a class member or property of the exported value) — not a hardcoded pattern for one class shape.

**Explicitly out of scope for this milestone** (do not fold in "while we're in there"): any other discovery capability, any risk/decision-policy change, any change to `design8.md`/`design9.md`. Scope creep here is exactly how a narrowly-defined fix turns into an ungoverned rewrite.

## Required discipline (repeat exactly, per prior rounds)

```text
implement → test known repos → freeze → select unseen repos → test → report
```

Same non-negotiables as v5/v6:
- No repository-specific rules (`if repository == ...`, `if filename == ...`, `if route == ...`).
- Held-out repositories selected only *after* the freeze commit, never inspected before.
- Failures reported with the same rigor as successes — a failed held-out result is valid evidence, not something to patch away before reporting.
- `design8.md`, `design9.md`, and the risk/decision policy (`RiskAssessment` semantics, `probability = UNKNOWN` handling, `risk_level` calculation, `RISK_PATTERNS`, `SENSITIVE_PATH_HINTS`, validation-selection policy, `ESCALATE`/`REQUIRE_ADDITIONAL_VALIDATION`/`ACCEPT`, cross-service test detection) remain frozen — untouched by this or any future architecture-discovery milestone.

## Status

Not started. Waiting for explicit engineering greenlight before any implementation work begins.
