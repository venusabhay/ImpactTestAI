# Vertical Slice — First Milestone Package

> ## STATUS: Stage 2B — Officially Accepted (frozen, no further work pending Stage 3 decision)
>
> **Milestone statement:** the vertical slice successfully identified a validation gap, selected a validation that exercised the real affected behavior, and uncovered a genuine authorization regression introduced by the change. The system correctly escalated the failed validation rather than allowing the change to proceed.
>
> **Verified, not merely asserted, before acceptance:**
> - Original code (no caching change): the security test **passes**.
> - Caching change present: the security test **fails**.
> - Repeated execution: **3/3 failures**, consistent timing — not a flake.
> - The real, unmodified `server.js` is exercised — no test-conditional code exists in it.
> - Real HTTP interaction — the exact call shape dependent services use, not an in-process mock.
> - The existing (pre-Stage-2B) test suite **passed** while missing the regression entirely.
> - The decision engine **automatically** changed its recommendation to `ESCALATE` — no rule was written to force this outcome.
>
> **Business decisions confirmed by the business owner:**
> 1. `ESCALATE` is the correct response when a selected validation fails on a potentially serious regression: do not auto-approve; hand off to a human for investigation/remediation. Automatic PR blocking, rollback, or remediation are explicitly out of scope for this MVP.
> 2. Leaving the defect unfixed in the experiment artifact is acceptable, because fixing it would destroy the evidence this milestone exists to demonstrate. **This defect is an intentionally retained demonstration defect — it is not an approved production change, it has not been committed or pushed anywhere, and it must not be merged, deployed, or otherwise treated as real.** It is labelled as such directly in the test file (`services/auth-service/verify-cross-service.integration.test.js`).
>
> **Next question, deliberately not yet asked:** not "can we build this?" — that's answered. It's "is this behavior valuable enough to justify turning this experiment into a product?" No Stage 3 (production evidence), no design8/design9 changes, and no new design document are planned until that question is answered.

---

**Target:** [social-media-mini](https://github.com/venusabhay/social-media-mini) (real repository, cloned locally to `/Users/abhay/git-venusabhay/social-media-mini`; nothing pushed back to it)
**Change analyzed:** a real code change made to `services/auth-service/server.js` — the `/verify` endpoint (called by both `post-service` and `user-service` on every authenticated request) was modified to add a 5-second in-memory cache of verification results, to reduce database load. This is a realistic, plausible engineering change with genuine correctness risk (a cached "valid" result could briefly outlive a token that should no longer be valid).
**Repository access used:** source code, tests, package/dependency manifests, CI workflow definitions, commit history. No production telemetry, incident history, or business documentation was available or used.

---

## A. The Change Risk & Validation Report

See [verify-cache-change-report.md](verify-cache-change-report.md) for the full report. Summary:

| Question | Answer |
| --- | --- |
| What changed? | `auth-service`'s `POST /verify` endpoint |
| What could be affected? | `auth-service` directly; `post-service` and `user-service` transitively (both call `/verify` on every authenticated request) |
| Risk | **HIGH** (business impact: HIGH, exposure: HIGH). Probability is reported as **UNKNOWN**, not estimated — see Limitations below. |
| Historical CI evidence (Stage 2) | 7 real CI runs examined; `auth-service`'s test job has 0 confirmed failures in that window (2 cancellations from unrelated sibling jobs, not counted). Additive evidence only — did not change the recommendation. |
| Cross-service validation (Stage 2B) | A real integration test now exists and was run — see below. It **found a genuine regression**. |
| Confidence | **LOW** overall — impact confidence HIGH, evidence confidence now **HIGH** (Stage 2B added a real cross-service test) |
| Recommended validation | `auth-service`'s test suite, now including a real cross-service integration test exercising the exact dependency relationship |
| Did it run? | Yes — real execution, not simulated |
| Result | **FAILED** — 13/14 tests passed; the new cross-service test caught a real authorization-bypass regression |
| Final decision | **ESCALATE** — do not proceed without human review |

## B. Evidence Available vs. Missing

**What the repository let us know, with direct evidence:**
- Exactly which route handler changed, and the line range of the change (source code).
- That two other services structurally depend on this endpoint, via literal HTTP calls found in their source (`post-service/server.js:131`, `user-service/server.js:130`).
- That an existing, real test file targets this endpoint by name (`auth.test.js`, 5 references to `/verify`), and — once built (Stage 2B) — that a real cross-service test could be constructed and run against the actual, unmodified `server.js`, over real HTTP, exactly as the dependent services call it.

**What the repository could not tell us — and the system said so explicitly, rather than guessing:**
- **How production-critical this path actually is.** Structural exposure (two calling services) is real evidence of *breadth*, but not of *severity* — we don't know if those services see 10 requests/day or 10,000/second in production.
- **Whether the existing tests meaningfully cover the change.** This is the most important limitation the system surfaced: `auth.test.js` does not import `server.js` at all. It re-implements its own local copy of the `/verify` route for testing. This is a structural fact discoverable from the repository alone (no import statement exists), and it means the 12 passing tests validate a *duplicate* of the route, not the actual changed file. The system flagged this and downgraded its confidence accordingly, rather than reporting "tests passed" as if that settled the question.
- **Historical failure/incident rate for this component.** No incident system was available in this slice.

## C. Validation Result

`npm test` was executed for real inside `services/auth-service` (Node 22, the repository's own Jest configuration) against the changed code, now including the Stage 2B cross-service integration test. **13 of 14 tests passed; one failed.** The failing test is the one that spawns the real, running `server.js` and drives it over real HTTP exactly as `post-service`/`user-service` do: it authenticated a user, primed the 5-second verification cache, deleted that user directly from the database, and immediately re-verified the same token. The live service returned `200 OK` with the stale cached user — a genuine authorization-bypass regression, not a test artifact. This is reported as a **confirmed, real result**, not a weak signal — the earlier suite's 12/12 pass was the weak signal; this one exercised the actual changed code path and found a real defect.

## D. Limitations

- **The test-suite gap described in B is repo-wide, not specific to this change.** None of the three backend services' original test files import their own `server.js`. This vertical slice happened to surface it because it directly affects how much weight to put on "tests passed" for this particular change — but it's a pre-existing characteristic of the repository, not something introduced by the change under review. (Stage 2B's new test is the one exception — it does import/exercise the real module, by design.)
- **Risk levels (HIGH / MEDIUM / LOW) are qualitative buckets from explicit, inspectable rules** (how many services structurally depend on the changed endpoint; whether the route name matches security-sensitive vocabulary; whether the diff introduces new in-memory state or caching). They are not calibrated against historical outcomes, because none exist yet for this repository. This is intentional and disclosed, not an oversight — see §6 of the business vision document on what a repo-only first version can and cannot know.
- **Probability is not estimated at all, on purpose** (policy version `repo-plus-ci-plus-cross-service-v4`). An earlier version of this tool derived a `probability: HIGH/MEDIUM/LOW` bucket from the count of diff risk-indicators — that conflated "a risk factor is present" with "a failure is likely," which is exactly the kind of overclaiming this platform is meant to avoid. It was caught and corrected: `probability` is reported as `UNKNOWN` with an explicit reason, and the underlying indicators are listed by name instead. The risk/validation rule version is stamped on every report so this kind of change is always traceable to a specific policy version.
- **The application bug the new test found was deliberately left unfixed.** Fixing it would remove the evidence Stage 2B was built to demonstrate. The correct next step is a human engineering decision (invalidate the cache on user deletion, or re-check user status on every verify regardless of cache), which is exactly what the `ESCALATE` decision calls for — this tool identifies and stops; it does not remediate.
- **Failure classification is still manual by design.** This tool did not determine "this is a genuine security regression" — a human reading the assertion message and stack trace did. The tool's own `classification` field for this outcome correctly says "requires human triage," even though, in this case, the triage is fairly obvious from the error message.

## E. Next-Value Opportunities

Based specifically on what remains missing after Stages 1, 2, and 2B — not a general wishlist:

1. **Extend the cross-service pattern to `post-service` and `user-service`'s own changes.** Stage 2B built one such test for one endpoint; the same pattern (spawn the real service, drive it over real HTTP, target the risk the change actually introduces) generalizes to other changes, but each one currently has to be hand-written — there's no automatic generation of this kind of test yet.
2. **Production telemetry for `/verify` call volume** would let the platform distinguish "structurally depended on by 2 services" (which we know) from "carries significant real traffic" (which we don't) — turning `exposure` from a structural guess into a measured quantity.
3. **A real deployment to observe Stage 3 against** — this bug was caught before release specifically because Stage 2B exists; the next open question is what the platform can learn from production behavior *after* a change ships, which needs a running, observable deployment that doesn't exist yet.

Deliberately not requested at this stage: incident-system access, business-flow documentation, or access to any other repository — none of them would have changed today's decision, and requesting them now would be exactly the "broad access because it might eventually help" pattern the business owner asked this slice to avoid.

---

## Stage 2 — CI/Test-Run History

Added one operational data source: this repository's real GitHub Actions run history (public API, no auth, no deployment). Result for this change: across 7 real `CI` workflow runs, `auth-service`'s test job (`Test Microservices (auth-service)`) has **0 confirmed failures** — 2 runs show it cancelled because a different, unrelated job failed elsewhere in the same run, which is explicitly not counted as evidence against `auth-service`. Full detail in [verify-cache-change-report.md](verify-cache-change-report.md)'s `HISTORICAL EVIDENCE (CI)` section.

**1. What did CI history add that repository-only analysis could not know?**
A real, evidenced answer to "has this area historically been unstable?" — previously listed only as an unknown. It also surfaced a real methodological trap worth naming: this repository's *overall* CI history looks alarming at a glance (4 of the earliest 7 runs show a failing workflow), but per-job detail shows those failures were in `user-service`'s tests and the frontend build — not `auth-service`. Reporting the repo-wide failure rate without that breakdown would have wrongly implicated `auth-service`.

**2. Did it materially improve the decision for this change?**
No — the recommendation stayed `REQUIRE_ADDITIONAL_VALIDATION`. That reason (the existing test suite doesn't exercise the changed code; two services structurally depend on the endpoint) is independent of `auth-service`'s clean CI history. A clean history is reassuring context, not grounds to relax the recommendation — and per the Stage 2 mandate, that's a valid result, not a failed experiment.

**3. Is CI history worth retaining as part of the product, or should it remain optional?**
Worth retaining as a standard evidence source. It's cheap (same repository, ~8 unauthenticated API calls, no new infrastructure), and it's the first source in this project that can distinguish "we have no data" from "we checked, and it's been stable." Whether it should ever feed into `risk_level` or `probability` numerically remains an open question this experiment didn't need to answer — this change happened to have a clean CI history, so the interesting case (a changed area with a real history of CI failures) is still untested.

---

## Stage 2B — Closing the Cross-Service Validation Gap

Every prior stage's report said the same thing: no cross-service integration test exists that would call the live, changed `/verify` endpoint from `post-service`/`user-service`. Stage 2B's mandate: don't just make the report say more tests passed — prove the vertical slice can identify **and execute** a validation that actually exercises the changed behavior across the services that depend on it.

**What was built:** a real integration test that spawns the actual, unmodified `services/auth-service/server.js` as a live child process against a real (ephemeral) MongoDB, and drives it over real HTTP with `axios` — the exact call `post-service`/`user-service`'s middleware makes. Its second test specifically targets the caching risk the platform's own risk assessment flagged: authenticate, prime the cache, delete the user, immediately re-verify the same token within the 5-second window.

**Result: the test failed for real.** The live service returned `200 OK` with a stale, cached user for a token belonging to a user that no longer existed — a genuine authorization-bypass regression that no prior test in this repository could have caught, because none of them import the real module or touch the cache at all. The pipeline's existing `any_failed` rule (unchanged since Stage 1) correctly turned this into **`ESCALATE`**.

**Why this matters more than another risk score:** the platform didn't just recommend caution — when the specific gap it identified was closed, the resulting validation caught a real defect. That is a direct demonstration of the product's central promise (§4, §7 of the business vision): validation proportional to identified risk, not blind trust in "tests passed." `POLICY_VERSION` is now `repo-plus-ci-plus-cross-service-v4`, reflecting the new evidence category (`CROSS_SERVICE_VALIDATION`) and the validation-selection rule change — probability remains unestimated, per v2/v3's boundary.

The bug itself was deliberately left unfixed in this exercise: fixing it would erase the evidence this stage was built to produce. The `ESCALATE` decision correctly hands the actual remediation choice to a human engineer.
