# Pilot Findings Report — 5 representative runs

**Baseline:** `main` @ `ba7529f`. `pilot-ci.yml` confirmed green at this exact commit (workflow run `33197877614` and later runs at the same SHA, all `success`). `TOOL_VERSION 0.8.0-pilot`, `POLICY_VERSION repo-plus-ci-plus-cross-service-plus-discovery-v9`.

**Method:** five real changes against five real repositories, chosen to hit the five requested categories, run with the unmodified `main` analyzer, `--npm-install`, and (except where noted) `--github-repo` for CI history. Raw reports, audit JSON, and two crash tracebacks are preserved in `case-reports/`. Nothing in `analyze_change.py` or `discovery.py` was changed to produce or "fix" any of these results.

---

## 1. Per-run evaluation

| # | Category (intended) | Repo / change | Observed | Inferred | Marked `UNKNOWN` | Selected validation | Validation outcome | Final decision | Do I (reviewing) agree? |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Low-risk comment/doc change | `developit/express-es6-rest-api`, real commit fixing a code-comment typo in `db.js` | 1-line comment-only diff; no route touched | `LOW` risk, no route-level impact | Historical incident rate, production exposure | `npm test` (→ `eslint src`) | **PASSED** | `REQUIRE_ADDITIONAL_VALIDATION` (overall confidence always `LOW`, per the fixed policy) | **Partially.** The risk read (`LOW`) is right and the evidence is honest. But recommending *additional validation* for a one-word comment fix, when the only "test" is a linter that already ran and passed, is more caution than a human would apply — see §3, Usability. |
| 2 | Normal app-code change with tests | `saisilinus/node-express-mongoose-typescript-boilerplate`, real commit migrating Mongoose `.remove()` → `.deleteOne()` in `user.service.ts`/`auth.service.ts` | Diff touches two service-layer files; a real test suite exists and imports the actual `app` | `LOW` risk, no route-level impact (service files aren't routes or route middleware) | "No route or middleware relationship discovered" for both changed files | `npm test` (jest, 7 suites) | **FAILED** — 6/7 suites failed with `Config validation error: "MONGODB_URL" is required`; 1 suite (6 tests) passed | `ESCALATE` | **No, not as stated.** The `FAILED` is real (jest did exit non-zero) but the *cause* is a missing environment variable at test-config load time, not a defect connected to this diff — the same category of pre-existing environment gap found earlier with `user-management-app`'s `JWT_REFRESH_SECRET`. See §3, Evidence-quality gap (recurring). |
| 3 | Change affecting a discovered route/component | Same repo, real commit "add bearerAuth" touching `passport.ts`, `auth.controller.ts`, `auth.service.ts` | `auth.controller.ts`'s 8 exported controller functions each connect, by name, to a real route registered in `auth.route.ts` | `HIGH` risk / `CRITICAL` business impact / `HIGH` exposure — 8 routes, security-sensitive path names | `passport.ts` (the actual auth-strategy config) flagged as no discoverable relationship; no test evidence for any of the 8 routes | `npm test` (jest) | **FAILED** — "No tests found, exiting with code 1" (no test files existed yet at this point in the repo's history) | `ESCALATE` | **Yes on the decision, with a caveat.** 8-route middleware-dependency discovery here is precise and correct — a real positive result. But `passport.ts` (arguably the *most* security-relevant file in this diff, since it defines the auth strategy itself) getting zero discovered relationship is a real detection gap — see §3. Also, "FAILED: no tests found" reads as an alarming top-line label for what is really "no test infrastructure existed yet," softened only in the fine print. |
| 4 | CI history provides useful evidence | `social-media-mini`, the persistent `/verify` caching change (Stage 2B) | 5-second in-memory cache in `auth-service`; 2 real callers | `HIGH` risk; real CI history: 7 runs examined, 0 confirmed failures for `auth-service`'s job | Historical incident rate, production exposure | Full `npm test` across `auth-service`/`post-service`/`user-service`, including the real cross-service integration test | **FAILED** — the real, reproduced authorization-bypass regression (stale cache returns a deleted user) | `ESCALATE` | **Yes, unambiguously.** This is the strongest result in the set: real evidence, a real validation that actually exercises the risk, a real defect caught, and CI history correctly used as *additive* context rather than folded into the decision. |
| 5 | Deliberately insufficient evidence | `user-management-app`, Change B (frontend password-confirmation validation) | Client-side-only change; no backend implication | `LOW` risk, empty impact | Historical incident rate, production exposure, "no test capability exists for the frontend" | None — `NOT AVAILABLE: INTEGRATION_TEST` (no test script) | No validation executed | `ESCALATE` | **Yes.** This is exactly the intended behavior: when there is genuinely nothing to run, the tool says so and defaults to the safe response, rather than inventing a validation or silently downgrading to "looks fine." |

**Two additional, unplanned events** occurred while producing cases 2 and 3, both severe enough to warrant their own section below rather than a table row: two separate unhandled Python exceptions **crashed the entire analysis, producing no report and no audit record at all.**

---

## 2. The two crashes (most important finding in this round)

### Crash A — CI-history fetch, case 2 (`case2-crash-traceback-1-ci-history.log`)

```
http.client.IncompleteRead: IncompleteRead(35612 bytes read, 15709 more expected)
...
File "analyze_change.py", line 692, in fetch_ci_history
    runs_data = _gh_api_get(...)
```

A transient, truncated HTTP response while fetching the repository's workflow-run list. `_gh_api_get()`/`fetch_ci_history()` have no exception handling around this network call at all. The exception propagated out of `main()` uncaught. **Not reproducible on retry** — the same command, run again seconds later, succeeded.

### Crash B — `npm install`, case 3 (`case3-crash-traceback-2-npm-install-timeout.log`)

```
subprocess.TimeoutExpired: Command 'npm install' timed out after 300 seconds
File "analyze_change.py", line 902, in run_validation
    install = subprocess.run(...)
```

This repository's real `npm install` genuinely takes close to 300 seconds (confirmed independently: a plain, unassisted `npm install` in the same checkout took **6 minutes**). The 300-second `npm install` timeout — unlike the validation-command timeout this exact pilot round just finished making configurable and safely handled — has **no `try`/`except subprocess.TimeoutExpired` around it at all**. **Reproducible**: happened on the first attempt; a retry succeeded only because the first attempt's `npm` child process kept running in the background past the point Python gave up on it (a known `subprocess.run(shell=True, timeout=...)` gotcha — the timeout doesn't reliably kill the actual child process it spawned) and had mostly finished installing by the second attempt.

**Why this matters more than any single decision-quality observation:** the entire value proposition tested in cases 1–5 — "the tool is honest about what it doesn't know" — only holds if the tool *produces output at all*. In both crashes, a pilot user would have received nothing: no report, no `ESCALATE`, no `INCONCLUSIVE`, not even an error message pointing at what went wrong — just a workflow run that failed outright, indistinguishable from a bug in the tool itself (which `PILOT.md` explicitly tells users to report as exactly that). This is a **regression risk on the exact reliability promise this round's own timeout work was meant to strengthen** — the validation-command path is now safe; the CI-history path and the `npm install` path are not, and both are exercised on every single real pilot run that supplies `--github-repo` and needs a fresh install.

This does not fit any of the seven requested categories cleanly (it's not a wrong decision — it's the absence of one). Recommend treating it as its own category: **reliability/robustness gap**, and the single highest-priority item to come out of this round.

---

## 3. Findings by category

### Working as intended
- Case 4 (`social-media-mini`): the whole pipeline — discovery, risk, CI history as additive-only evidence, real cross-service validation, decision — worked exactly as designed and caught a real defect.
- Case 5 (`user-management-app` Change B): correct, honest "insufficient evidence" behavior with no validation invented.
- Case 3's 8-route middleware-dependency discovery: precise, correct, no false positives or omissions among the routes it did find.
- Probability is `UNKNOWN` in every single run, with no exceptions — the core invariant held across all 5 cases plus both crash investigations.

### Usability/documentation issue
- Case 1: recommending `REQUIRE_ADDITIONAL_VALIDATION` for a one-word comment-typo fix, immediately after the only available check (`eslint`) already ran and passed, is *technically* consistent with the documented, disclosed policy (confidence is structurally capped at `LOW`; see the `ACCEPT`-unreachable finding from the validation-timeout work) — but a first-time pilot user seeing this on the most trivial possible change is likely to read it as the tool being unhelpfully cautious rather than understand the underlying reason, unless they've already read `PILOT.md`'s note on this. Not a new finding (documented in `PILOT.md` already), but this is the first time it showed up on a change trivial enough to make the gap between "recommendation" and "human judgment" this visible.
- Case 3: a `FAILED` validation outcome whose actual cause is "zero test files existed at this point in history" reads, at a glance, as a real test failure. The fine-print classification is honest ("Unknown / insufficient evidence — requires human triage"), but the bold top-line `**FAILED**` is the first thing anyone reads.

### Evidence-quality gap
- **Recurring across pilot repositories, second occurrence:** missing environment variables required for a test suite to even initialize (case 2: `MONGODB_URL`; previously: `user-management-app`'s `JWT_REFRESH_SECRET`). Two independent repositories, two independent required env vars, same failure shape — a real `FAILED`/exit-1 result that a human immediately recognizes as environment setup, not a code defect, but which the tool cannot currently distinguish from a genuine regression. This is now a pattern, not a one-off — worth weighing as a candidate for the next milestone (not decided here).
- **New, distinct from the Archify rate-limit finding:** `fetch_ci_history()`'s workflow filename is hardcoded to `.github/workflows/ci.yml` with no override. Case 2's repository has 53 real workflow runs with genuine pass/fail history, on a workflow named `.github/workflows/node.js.yml` — confirmed directly against GitHub's API. Every one of those 53 runs is invisible to the analyzer purely because of the filename assumption, and it fails silently into "insufficient evidence" rather than surfacing that a differently-named workflow exists. In a small, unscientific sample (3 of 5 case repositories checked for a workflow directory; only `social-media-mini`, already known, happened to use `ci.yml`), this filename mismatch looks at least as common as Archify's rate-limiting problem — possibly more so, since it doesn't require a CI-heavy repository, just a different naming convention.
- **Rate limiting, investigated as instructed — did not clearly recur this round.** Case 2's repository (53 runs) hit the filename-mismatch problem before rate limiting had a chance to matter. Case 4's repository (`social-media-mini`, 7 runs) fetched cleanly with no rate-limit errors. Case 1 and case 3's repositories returned 0 runs examined (too new/small a workflow history to test rate limiting either way). **This round produced one data point where CI history was reachable at all (case 4) and it did not hit rate limits** — consistent with your instruction not to build a fix yet, since the Archify occurrence remains a single data point and this round didn't add a second one. The filename-mismatch gap, not rate limiting, is what actually blocked CI history in this round's repositories.

### Detection gap
- Case 3: `passport.ts` — the file that actually defines the authentication strategy used by the whole app — produces zero discovered relationship to any route. The 8 controller functions in `auth.controller.ts` connect correctly because they're referenced by name directly in route registrations; `passport.ts` is wired in indirectly (via Passport's own strategy-registration API, not a route-registration call our discovery mechanism recognizes), so a change to the authentication mechanism itself is invisible to impact analysis even though it is, if anything, more security-critical than the controller layer that *does* get discovered. This is a real, disclosed scope boundary (not a bug), but worth naming precisely: **auth-strategy/middleware-configuration files that aren't referenced as a route-call argument are structurally invisible**, regardless of how central they are.

### Validation gap
- The two crashes (§2) are best understood as validation-*pipeline* gaps: the mechanism that already exists to turn "couldn't run this" into an honest `INCONCLUSIVE` (built and tested earlier this round) is not applied consistently to every subprocess/network call the pipeline makes — only to the one call this round's own milestone touched.

### Potential product requirement
- Whether `REQUIRE_ADDITIONAL_VALIDATION` should ever soften to something like `ACCEPT` for a change this trivial (case 1) is the same open policy question already raised and deliberately deferred (the `ACCEPT`-reachability question from the validation-timeout work) — not re-opened here, just re-confirmed as still live and now with a second concrete example.
- Whether the CI-history feature should support more than one workflow filename (or discover the right one from the repository, generically — e.g., any workflow that runs on `push`/`pull_request` and appears to run tests) is a real product question raised by this round's evidence, not decided here.

---

## 4. Direct answer to the specific investigation requested

> Does the CI-history rate-limit problem recur across several pilot repositories?

**Not established either way by this round** — only one of the five repositories (case 4) had CI history that was actually reachable (right filename, real run history), and it did not hit rate limits. The other repositories were blocked from testing this question at all by a *different* evidence-quality gap (filename mismatch, or too little history to matter). Per your instruction, no fix is proposed for rate limiting from this round's evidence — there still isn't a second data point for it. The filename-mismatch gap, however, now has two data points against it happening at all when checked (case 2 confirmed; case 1/3's repos have too little CI history to say either way) and is a stronger, more directly evidenced candidate for "the next repeated problem" than rate limiting is, *if* engineering capacity goes toward CI-history evidence quality next — though per your closing instruction, that choice is not being made here.

---

## 5. What this round does *not* recommend

Per instruction, no engineering has been started from this round's findings. In particular, not proposed or implemented here:
- A fix for either crash (§2) — flagged as the highest-priority candidate, not actioned.
- A fix for the CI-history filename assumption.
- A fix for the missing-env-var pattern (case 2, echoing `user-management-app`).
- Any change to `passport.ts`-style discovery.
- Any change to the `ACCEPT`-reachability/confidence-scoring question.

The immediate ask — run the pilot, collect evidence, identify the next *repeated* problem rather than the next theoretically useful feature — is answered above: the clearest repeated problem this round surfaced is not a decision-quality issue at all, but the reliability gap in §2, discovered by accident rather than by design, on two of five runs.
