# Vertical Slice — First Milestone Package

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
| Risk | **HIGH** (business impact: HIGH, probability: HIGH, exposure: HIGH) |
| Confidence | **LOW** overall — impact confidence is HIGH (directly observed in code), but evidence confidence is LOW (see limitations below) |
| Recommended validation | Run `auth-service`'s existing test suite (`npm test`) — the best available real validation, with an explicit caveat attached |
| Did it run? | Yes — real execution, not simulated |
| Result | PASSED (12/12 tests) |
| Final decision | **REQUIRE ADDITIONAL VALIDATION** — not a plain "proceed" |

## B. Evidence Available vs. Missing

**What the repository let us know, with direct evidence:**
- Exactly which route handler changed, and the line range of the change (source code).
- That two other services structurally depend on this endpoint, via literal HTTP calls found in their source (`post-service/server.js:131`, `user-service/server.js:130`).
- That an existing, real test file targets this endpoint by name (`auth.test.js`, 5 references to `/verify`).
- That the existing tests actually passed when run against the changed code (real `npm test` execution, not assumed).

**What the repository could not tell us — and the system said so explicitly, rather than guessing:**
- **How production-critical this path actually is.** Structural exposure (two calling services) is real evidence of *breadth*, but not of *severity* — we don't know if those services see 10 requests/day or 10,000/second in production.
- **Whether the existing tests meaningfully cover the change.** This is the most important limitation the system surfaced: `auth.test.js` does not import `server.js` at all. It re-implements its own local copy of the `/verify` route for testing. This is a structural fact discoverable from the repository alone (no import statement exists), and it means the 12 passing tests validate a *duplicate* of the route, not the actual changed file. The system flagged this and downgraded its confidence accordingly, rather than reporting "tests passed" as if that settled the question.
- **Historical failure/incident rate for this component.** No incident system was available in this slice.

## C. Validation Result

`npm test` was executed for real inside `services/auth-service` (Node 22, the repository's own Jest configuration) against the changed code. All 12 existing tests passed. Per the point above, this result is reported as a **weak, indirect signal** rather than confirmation — the report is explicit that a pass here does not prove the cache logic itself is correct, because no existing test exercises it.

## D. Limitations

- **The test-suite gap described in B is repo-wide, not specific to this change.** None of the three backend services' test files import their own `server.js`. This vertical slice happened to surface it because it directly affects how much weight to put on "tests passed" for this particular change — but it's a pre-existing characteristic of the repository, not something introduced by the change under review.
- **Risk levels (HIGH / MEDIUM / LOW) are qualitative buckets from explicit, inspectable rules** (how many services structurally depend on the changed endpoint; whether the route name matches security-sensitive vocabulary; whether the diff introduces new in-memory state or caching). They are not calibrated against historical outcomes, because none exist yet for this repository. This is intentional and disclosed, not an oversight — see §6 of the business vision document on what a repo-only first version can and cannot know.
- **No cross-service integration test exists** that would call the live, changed endpoint from `post-service` or `user-service`. The system recorded this as an explicitly rejected validation option with a stated reason, not a silent gap.
- **Failure classification is manual.** If a validation had failed, this slice does not attempt to automatically distinguish a genuine regression from a flaky test or infrastructure issue — it flags failures as requiring human triage rather than guessing.

## E. Next-Value Opportunities

Based specifically on what *this* run showed was missing — not a general wishlist:

1. **A cross-service integration test capability** would directly close the largest gap this run surfaced: right now, nothing in the repository can confirm that `post-service` and `user-service` still work correctly against the changed `/verify` behavior. This would provide the single largest confidence improvement for changes to this exact endpoint.
2. **Production telemetry for `/verify` call volume** would let the platform distinguish "structurally depended on by 2 services" (which we know) from "carries significant real traffic" (which we don't) — turning `exposure` from a structural guess into a measured quantity.
3. **CI/test-run history** (pass/fail rates over time for this service) would let future risk assessments account for whether this area of the code has a track record of breaking, rather than assessing each change in isolation.

Deliberately not requested at this stage: incident-system access, business-flow documentation, or access to any other repository — none of them would have changed today's decision, and requesting them now would be exactly the "broad access because it might eventually help" pattern the business owner asked this slice to avoid.
