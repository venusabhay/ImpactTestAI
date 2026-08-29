# Environment/setup failure classification: investigation

## Objective and scope

Determine whether validation failures caused by repository environment/
setup problems (missing configuration, absent test infrastructure,
broken dependency installs, flaky test-support services) recur often
enough, and are distinguishable enough from genuine test failures, to
justify a future implementation milestone.

**This is an investigation only.** No analyzer behavior was changed to
produce it. Confirmed by `git diff main..investigate/environment-failure-classification
-- slice/` being empty for every `.py` file (see the Completion gate at
the end of this document).

Not in scope, per instruction, and not attempted: repository-specific
exceptions, environment-variable allowlists, retries, or any change to
`POLICY_VERSION`, `TOOL_VERSION`, risk scoring, confidence scoring, or
recommendation logic.

## Baseline commit

`main` @ `e57cf53` (post-`chore/repository-organization`). Branch
`investigate/environment-failure-classification` created from this
commit. Baseline test run: **113/113 passing** (`python3 -m pytest
slice/tests/ -q`), confirmed at both the start and end of this
investigation — no drift, no source changes in between.

## Methodology

Real repositories and real changes were run through the actual
analyzer (`analyze_change.py`) exactly as a pilot user would invoke it,
or reused from evidence already gathered and preserved in prior,
independent pilot rounds (cited by source file, not re-described from
memory). Where a case was freshly re-run for this investigation, the
full raw `npm install`/`npm test` output was captured before any
interpretation, and — where the failure's cause was not obvious from a
single run — the same command was re-run against the unmodified
baseline commit to determine whether the failure was actually caused by
the change under analysis at all.

No repository was chosen because it was expected to demonstrate the
hypothesis: 5 of the 7 cases below were originally selected in earlier,
independent pilot milestones for unrelated reasons (validation-timeout
tuning, CI-workflow-discovery evidence, the original architecture-
discovery pilot) and are reused here by citation; only 2 (the
`user-management-app` re-run and the fresh `saisilinus` install
attempt) were run specifically for this investigation, and both were
run once each, not repeated until a desired result appeared.

## Repository/sample selection

| # | Repository | Commit / change | Runtime | Package manager | Invocation |
|---|---|---|---|---|---|
| 1 | `saisilinus/node-express-mongoose-typescript-boilerplate` | Real commit migrating Mongoose `.remove()`→`.deleteOne()` (`user.service.ts`/`auth.service.ts`) | Node (historical run, version not separately recorded — see Limitations) | npm | `analyze_change.py ... --npm-install --github-repo saisilinus/...` |
| 2 | `saisilinus/node-express-mongoose-typescript-boilerplate` | Real "add bearerAuth" commit, at a point in this repository's history before any test files existed | Node (historical run) | npm | same, `--npm-install` |
| 3 | `venusabhay/social-media-mini` | Real, hand-authored `/verify` caching change (Stage 2B vertical-slice demonstration) | Node (historical run) | npm | `analyze_change.py ... --npm-install --github-repo venusabhay/social-media-mini` |
| 4 | `developit/express-es6-rest-api` | Real commit, one-line comment fix in `db.js` | Node (historical run) | npm | `analyze_change.py ... --npm-install` |
| 5 | `user-management-app` (local, `venusabhay/user-management-app`) | `change-a-api-cache.patch` applied to `9515655` (`First-commit`) | Node v22.23.2 | npm 10.9.8 | `analyze_change.py user-management-api --against HEAD --npm-install`, then raw `npm test` run directly, twice (once against the patched tree, once against unmodified `9515655` for baseline comparison) |
| 6 | `saisilinus/node-express-mongoose-typescript-boilerplate` | Same checkout as #1/#2 (`/tmp/pilot-case2b`), `node_modules`/`package-lock.json` removed to force a fresh install | Node v22.23.2 | npm 10.9.8 | `npm install` directly, then `analyze_change.py ... --npm-install` |
| 7 | `tt-a1i/archify` (branch `codex/fix-site-language-continuity`) | Real PR branch vs. `main` | Node (historical run) | npm | `analyze_change.py ... --npm-install --validation-timeout-seconds 600`, run 3 times on the identical commit |

Coverage against the requested variety:
- **Missing environment/configuration, ≥2 repositories:** #1 (`MONGODB_URL`) and #5 (JWT secret — see §5, this shape looks nothing like #1's).
- **Genuine assertion/test regression:** #3 (a real, intentionally-introduced authorization-caching security defect, independently verified 3/3 reproducible on the changed code and passing on the original).
- **Dependency/install failure:** #6.
- **Tests succeed without special configuration:** #4.
- **Established test suite:** #7 (748 real tests).
- **Sparse/no test infrastructure:** #2.

## Per-case results and raw failure categories

### Case 1 — `saisilinus/...`, Mongoose refactor — **missing environment/configuration**

Source: [`pilot/cases/2026-08-28-pilot-round/case-reports/case2-service-layer-refactor.md`](../../cases/2026-08-28-pilot-round/case-reports/case2-service-layer-refactor.md).

```
FAIL src/modules/token/token.model.test.ts
  ● Test suite failed to run

    Config validation error: "MONGODB_URL" is required

      at Object.<anonymous> (src/config/config.ts:30:9)

Test Suites: 6 failed, 1 passed, 7 total
Tests:       6 passed, 6 total
```

Analyzer: `FAILED` (exit 1), classification `Unknown / insufficient
evidence -- requires human triage`, decision `ESCALATE`.

**Structural signature:** Jest itself labels this `Test suite failed to
run` — a distinct category from a normal test failure, emitted when an
error is thrown while *loading* the suite (here, at module-level config
validation), before any `test(...)`/`it(...)` body executes. Note also:
**6 tests still passed** — the suites that didn't import the
config-dependent module ran and passed normally, so the failure is
scoped to exactly the suites that touch configuration, not the whole
run.

### Case 2 — `saisilinus/...`, pre-test-infrastructure commit — **no test infrastructure**

Source: [`pilot/cases/2026-08-28-pilot-round/case-reports/case3-auth-middleware-change.md`](../../cases/2026-08-28-pilot-round/case-reports/case3-auth-middleware-change.md).

```
No tests found, exiting with code 1
Run with `--passWithNoTests` to exit with code 0
```

Analyzer: `FAILED` (exit 1), `ESCALATE`.

**Structural signature:** this is Jest's own literal, verbatim message
for "zero test files matched" — not repository-authored text at all.
Unambiguous, and identical across every repository using Jest.

### Case 3 — `social-media-mini`, `/verify` caching change — **genuine test/assertion failure**

Source: [`pilot/cases/2026-08-28-pilot-round/case-reports/case4-verify-caching-cihistory.md`](../../cases/2026-08-28-pilot-round/case-reports/case4-verify-caching-cihistory.md); underlying defect independently verified in
[`pilot/cases/vertical-slice-package.md`](../../cases/vertical-slice-package.md) (3/3 reproducible failures on the changed code, 0/3 on the original).

```
FAIL ./verify-cross-service.integration.test.js
  ● Cross-service: /verify as actually called by dependent services ›
    SECURITY REGRESSION CHECK: a deleted user must not remain
    authorized via the verification cache

    SECURITY REGRESSION: /verify returned status 200 ... for a token
    belonging to a user deleted moments earlier. The 5-second
    verification cache introduced in this change authorized a request
    that should have been rejected...
```

Analyzer: `FAILED`, `ESCALATE` for `auth-service`; the other two
services in the same change (`post-service`, `user-service`) `PASSED`.

**Structural signature:** the failure happens *inside* a running test
(`throw new Error(...)` in the test body itself), not at suite-load
time — the opposite structural shape from Cases 1/2. This is the
correct, honest outcome: a real defect, correctly surfaced as `FAILED`.

### Case 4 — `express-es6-rest-api`, comment fix — **clean pass**

Source: [`pilot/cases/2026-08-28-pilot-round/case-reports/case1-trivial-comment-fix.md`](../../cases/2026-08-28-pilot-round/case-reports/case1-trivial-comment-fix.md).

`npm test` (`eslint src`) — `PASSED`, exit 0. No configuration, no
database, no external service. Included as the "nothing to detect"
control case.

### Case 5 — `user-management-app`, API-cache change — **ambiguous: looks like a genuine failure, is actually environment-caused**

Freshly run for this investigation. Two different raw failure shapes
were observed across two separate invocations of the *identical*
unmodified test suite, on the *same* machine, minutes apart:

**Run A (cold `mongodb-memory-server` cache):**
```
Starting the MongoMemoryServer Instance failed, enable debug log for
more information. Error:
 GenericMMSError: Instance failed to start within 10000ms
    at Timeout.<anonymous> (node_modules/mongodb-memory-server-core/
    src/util/MongoInstance.ts:383:21)
...
Test Suites: 1 failed, 1 total
Tests:       18 failed, 18 total
Time:        111.952 s
```

**Run B (warm cache, ~20s later run):**
```
console.error
    JWT verification failed: JsonWebTokenError {
      name: 'JsonWebTokenError',
      message: 'secret or public key must be provided'
    }
      at error (middleware/authMiddleware.js:35:15)
...
  ● DELETE /api/users/:id › should return 404 for non-existent user
    expect(received).toBe(expected)
    Expected: 404
    Received: 401
...
Test Suites: 1 failed, 1 total
Tests:       7 failed, 11 passed, 18 total
Time:        19.464 s
```

Run B's per-test failures look, on their face, exactly like ordinary
assertion mismatches (`Expected: 404, Received: 401`) — indistinguishable
in shape from Case 3's genuine defect. The actual cause, confirmed by
re-running the identical `npm test` against the unmodified baseline
commit (`9515655`, no patch applied): **the exact same 7 failed / 11
passed result occurs with no code change at all.** The root cause is
`jsonwebtoken` throwing `"secret or public key must be provided"` —
caught by a `try`/`catch` inside `authMiddleware.js`, converted into an
ordinary-looking `401` HTTP response, which then fails an ordinary-
looking test assertion many call-frames away from the actual missing
secret. `dotenv` itself reports `injecting env (0) from .env` —
confirming zero environment variables were loaded, consistent with the
missing-secret theory.

Analyzer (real run, this investigation): `FAILED`, `ESCALATE`,
classification `Unknown / insufficient evidence -- requires human
triage`.

**This is the most important finding in this investigation.** The same
underlying category of problem (a missing required secret) that
crashed loudly and structurally-distinctly in Case 1 here gets *caught*
by application code and re-emerges as a completely ordinary-shaped
per-test assertion failure. No purely structural, single-run signal
(suite-level crash vs. per-test failure) distinguishes this case from
Case 3's genuine defect. It was only identified by (a) comparing
against an unmodified baseline run and (b) recognizing a specific
third-party library's own error string (`jsonwebtoken`'s "secret or
public key must be provided") — neither of which the analyzer does or
safely could do generically today (see §Generic detection feasibility).

### Case 6 — `saisilinus/...`, forced fresh install — **dependency/install failure (already correctly handled)**

Freshly run for this investigation, `node_modules`/`package-lock.json`
removed first.

```
npm error code ERESOLVE
npm error ERESOLVE could not resolve
npm error
npm error While resolving: node-mocks-http@1.18.1
npm error Found: @types/express@4.17.13
...
npm error Conflicting peer dependency: @types/express@5.0.6
```

Analyzer: `npm install` → **`INCONCLUSIVE`**, classification
`INFRASTRUCTURE (dependency install failed)` — **not** `FAILED`. This
is the 0.9.0 pipeline-fail-safe milestone's existing behavior working
correctly; included here as a contrast case, not a new finding. `npm`'s
own error format (`npm error code ERESOLVE`) is a fully generic,
package-manager-level signal, already reliably distinguishable from a
test failure by the fact that it occurs during the *install* step, a
structurally separate phase the analyzer already tracks independently.

### Case 7 — `tt-a1i/archify` — **ambiguous: large healthy suite, one flaky test**

Source: [`docs/decisions/VALIDATION_TIMEOUT_DISPOSITION.md`](../../../docs/decisions/VALIDATION_TIMEOUT_DISPOSITION.md), §7–8 (prior, independent investigation; not re-run here).

748 real tests. Across 3 runs of the *identical* commit: one run
completed 723 passed / 0 failed / 25 skipped; two runs completed 722
passed / 1 failed / 25 skipped, both times the same single test (a
`cli: deliver --open` test involving Unicode/quoted paths and the
macOS `open` command). Analyzer: `FAILED`, `ESCALATE`.

**Structural signature:** the failure is a normal per-test failure
(structurally identical to Case 3's genuine defect and Case 5's
environment-caused failure) — no textual or structural marker
distinguishes it. The *only* signal that revealed this as
environment/OS-dependent flakiness rather than a real defect was
**re-running the identical commit multiple times and observing
inconsistent results** — a signal the analyzer does not, and by design
should not (retries are explicitly out of scope), collect from a single
analysis run.

## Human-vs-analyzer classification comparison

| Case | Analyzer result | Human classification | Evidence | Generic signal? | Confidence |
|---|---|---|---|---|---|
| 1. `saisilinus` Mongoose | `FAILED`/`ESCALATE` | Missing environment/configuration | `Config validation error: "MONGODB_URL" is required`, Jest `Test suite failed to run` | **Yes** — Jest's own suite-load-failure marker, framework-level, not repo-specific | High |
| 2. `saisilinus` pre-tests | `FAILED`/`ESCALATE` | No test infrastructure | `No tests found, exiting with code 1` | **Yes** — Jest's own literal, verbatim message | High |
| 3. `social-media-mini` | `FAILED`/`ESCALATE` | Genuine test/assertion failure (real defect) | Assertion thrown inside a running test; independently reproduced 3/3 on changed code, 0/3 on original | N/A — correctly classified today | High |
| 4. `express-es6-rest-api` | `PASSED` | Clean pass | exit 0 | N/A | High |
| 5. `user-management-app` | `FAILED`/`ESCALATE` | **Should be:** validation could not meaningfully execute — missing environment secret, unrelated to the change | Ordinary-shaped assertion failures (`Expected 404, Received 401`); root cause only visible via baseline diff + library-specific error string | **No** — structurally identical to a genuine defect; only detectable via baseline comparison or a library-specific string match | **Low** (for any purely-generic, single-run detector) |
| 6. `saisilinus` install | `INCONCLUSIVE`/`ESCALATE` (already correct) | Dependency/install failure | `npm error code ERESOLVE` | Yes, and already implemented (0.9.0) | High |
| 7. `tt-a1i/archify` | `FAILED`/`ESCALATE` | **Ambiguous** — likely environment/OS-dependent flake, not proven | Ordinary-shaped test failure; only revealed by re-running 3x | **No** — structurally identical to a genuine defect; only detectable via repeated runs | **Low** |

**False positives for a naive generic detector, specifically:** if a
detector were built to treat *any* per-test failure mentioning an
auth/config/secret-shaped error as "environment, not a defect," Case 3
(the genuine security regression) also involves authorization
behavior and a thrown error — a detector tuned loosely enough to catch
Case 5 risks also downgrading Case 3's real defect. This is not
hypothetical: Case 3 and Case 5 are structurally the same shape
(assertion/exception thrown inside a running test); the only thing that
tells them apart is knowing, independently, what the underlying string
means and whether it is present on the unmodified baseline. A detector
that can't do that safely and generically should not guess.

## Generic detection feasibility

Two genuinely generic, safe signals were found, both purely structural
and framework-level (not repository- or variable-specific):

1. **Jest's "Test suite failed to run" vs. a normal per-test failure**
   distinguishes "something broke before any test executed" (Cases
   1, 2) from "a test ran and its assertion failed" (Cases 3, 5, 7).
   This is real and safe — it comes from Jest's own test-runner
   protocol, not from inspecting error text.
2. **npm's own `npm error code ERESOLVE` / non-zero install exit**
   already distinguishes install-phase failures — already implemented
   (0.9.0), included here only as a confirmed-safe reference point.

Signal 1 would correctly and safely flag Cases 1 and 2. It would
**not** flag Case 5 or Case 7 — both manifest as ordinary per-test
failures, the same shape as a real defect (Case 3). No safe, generic,
single-run signal was found that distinguishes Case 5/7's shape from
Case 3's. The candidates considered and rejected:

- **Matching specific error strings** (`"secret or public key must be
  provided"`, `"is required"`, etc.) — this is exactly the kind of
  variable/library-specific heuristic the instruction excludes, and
  Case 3 vs. Case 5's structural identity shows why: the string alone
  doesn't prove absence of a real defect.
- **Baseline comparison** (re-run the unmodified commit, diff the
  result) — would have correctly caught Case 5, but doubles validation
  cost on every single analysis (every run becomes two runs), and is a
  substantially larger scope change than "classify a failure," not
  demonstrated or requested here.
- **Repeated runs on the same commit** (would have caught Case 7) — is
  explicitly the "retries" item, out of scope by instruction.

**Answer to the investigation's central technical question:** setup/
configuration failures can be identified generically, safely, and
without repository-specific knowledge **only for the narrow subset that
crashes before any test executes** (a real, but partial, capability).
The broader and — in this sample — more common shape, where an
environment problem is silently caught and re-emerges as an ordinary
test failure deep inside application code, has no generic, single-run
signal that doesn't also risk misclassifying a genuine defect.

## Recurrence measurement

Of 7 cases examined:

- **2 of 7** exhibited a setup/configuration failure with a safe,
  generic, structural signal (Cases 1, 2 — both missing-environment-
  variable shaped, both crash at suite-load time).
- **1 of 7** was a genuine test/assertion failure, correctly classified
  today (Case 3).
- **1 of 7** passed cleanly, nothing to detect (Case 4).
- **2 of 7** were ambiguous — present as ordinary test failures but are
  actually environment-caused (Cases 5, 7) — **these are the cases
  where a generic detector would need to act, and exactly where no safe
  generic signal was found.**
- **1 of 7** was a dependency/install failure, already correctly
  handled (Case 6).

A generic classifier built around the one safe signal found (Case 1/2's
structural marker) would have been **correct in 2 of 2** applicable
cases and **silent (correctly declining to classify) in the remaining
5** — it would not have misclassified anything, but it also would not
have helped with the majority of the setup-shaped failures actually
observed (2 of 4 setup-shaped cases: 5 and 7).

**This is a sample of 7, not a statistically significant study.** No
claim is made about the true population rate of any category across
real-world repositories generally. The specific numbers above describe
only what was observed in this specific, deliberately-varied-but-small
set, gathered opportunistically across several independent pilot
rounds plus two fresh runs.

## Product impact

Mapping to the three outcomes named in the instruction:

- **(A) Classification problem** (the validation result itself should
  become a different state) — **not supported.** Every case examined
  that is genuinely a setup/environment issue also genuinely failed to
  produce a validated result — `FAILED`/`ESCALATE` is not a wrong
  *decision* in any of Cases 1, 2, 5, or 7; a human still cannot
  proceed without investigating. Changing the result itself (e.g. to a
  new state) wasn't shown to be necessary or safe to do generically.
- **(B) Evidence-description problem** (stay `FAILED`, but say more) —
  **partially supported, narrowly.** For the safe subset (Cases 1, 2),
  a report could say "this failure occurred during test-suite
  initialization, before any test executed" using only Jest's own
  `Test suite failed to run` marker — zero repository-specific
  knowledge required. But note: **the raw evidence enabling a human to
  reach this same conclusion is already in the report today** — the
  existing `stdout_tail` already contains the literal `Config
  validation error: "MONGODB_URL" is required` / `No tests found`
  text, in full, in every case examined. The marginal value of adding
  a structured label on top of already-visible raw text is real but
  small.
- **(C) No actionable problem** — **the stronger conclusion for the
  majority of cases.** For Cases 5 and 7 — arguably the more consequential
  and more common shape in this sample — no safe generic mechanism was
  found, and the existing `classification: Unknown / insufficient
  evidence -- requires human triage` field is already an honest,
  correct disclaimer: the tool is not pretending to know the cause, and
  the raw stdout is available for a human to judge, exactly as it
  should be for a case where the tool genuinely cannot tell.

## Interaction with existing fail-safe behavior (regression checks only)

All confirmed unchanged, via both the existing test suite (113/113
passing throughout) and live verification performed during this
investigation:

- **Validation timeouts remain `INCONCLUSIVE`:**
  `test_run_validation_reports_inconclusive_on_timeout` and related
  tests, unchanged, passing.
- **`npm install` timeouts remain `INCONCLUSIVE`:**
  `test_run_validation_npm_install_timeout_is_inconclusive_not_a_crash`,
  unchanged, passing; also directly reconfirmed live in Case 6 above
  (`INCONCLUSIVE`, `INFRASTRUCTURE (dependency install failed)`, not
  `FAILED`).
- **CI retrieval failures remain `UNKNOWN`/insufficient evidence:**
  `test_fetch_ci_history_handles_incomplete_read_without_crashing` and
  related tests, unchanged, passing.
- **No failure path produces fabricated evidence:** confirmed by the
  same tests (`service_failures == 0`, `service_successes == 0`, empty
  `service_job_results` on every failure path) — unchanged.
- **`INCONCLUSIVE` still results in `ESCALATE`:**
  `test_timeout_outcome_never_reaches_accept_or_require_additional_validation`
  and `test_install_timeout_outcome_still_escalates`, unchanged,
  passing.

No already-closed reliability finding was reopened or touched.

## Limitations

- Sample size is 7 cases across 5 distinct repositories — small, and
  explicitly not claimed to be statistically representative.
- 5 of 7 cases are reused from evidence gathered for other purposes in
  earlier milestones; only 2 were run fresh specifically for this
  investigation. This reduces selection bias (nothing was hand-picked
  to prove the hypothesis) but also means the sample wasn't designed
  from scratch to be maximally representative either.
- Historical cases (1–4, 7) do not have their exact Node/npm version
  separately recorded from the time they were originally run — only
  `TOOL_VERSION` is preserved in those reports. Cases 5 and 6 (run
  during this investigation) used Node v22.23.2 / npm 10.9.8.
- Case 5's root cause (a missing JWT secret manifesting as ordinary
  assertion failures) was identified through investigation specific to
  this repository's code (reading `authMiddleware.js`, tracing the
  `try`/`catch`) — this is exactly the kind of manual diagnosis a
  generic, repository-agnostic detector would not be able to perform,
  which is itself evidence for the difficulty being real, not
  investigator error.
- This investigation did not attempt to survey a broader population of
  repositories beyond convenience/availability (previously-touched
  pilot repositories plus one local fixture); a future round drawing a
  fresh, larger, unrelated sample could find a different balance.

## Recommendation

**DEFER**

The evidence shows environment/setup failures do recur (4 of 7 cases
in this sample involved some form of setup/configuration issue), but
the sample also concretely demonstrates that the *more common and more
consequential* shape of that problem — a missing-configuration issue
silently caught by application code and re-emerging as an ordinary
per-test failure (Cases 5 and 7, 2 of 4 setup-shaped cases) — has no
safe, generic, single-run signal that doesn't also risk misclassifying
a genuine defect (demonstrated directly by Case 3's structural
identity to Case 5). The one safe signal found (Jest's suite-load-
failure marker) is real but narrow, covers only 2 of 4 setup-shaped
cases in this sample, and its marginal value is reduced by the fact
that the raw diagnostic text it would summarize is already visible in
today's report. Per the stated decision principle: the bar is not
"can some environment failures be detected" (yes, narrowly) but
whether they occur frequently enough, are detectable generically
enough, and are misleading enough to justify a product change — for
the majority shape observed here, that bar is not met. Preserve this
finding; revisit if a future pilot round accumulates more cases of the
safe, narrow (suite-load-failure) shape specifically, or if a
genuinely safe way to handle the harder (in-test, silently-caught)
shape is found.

---

## Completion gate

- [x] No analyzer/source logic changed — `git diff main.. -- '*.py'` on
  this branch is empty.
- [x] No policy/risk/recommendation logic changed — same.
- [x] No workflow changes — `.github/workflows/` untouched.
- [x] No repository-specific heuristics were introduced — none
  proposed or implemented; the one safe signal identified is a Jest
  framework-level marker, not tied to any repository, variable name, or
  library-specific string.
- [x] Existing tests pass — 113/113, confirmed at both start and end.
- [x] Real repositories were examined — 5 distinct real repositories,
  7 cases.
- [x] Raw validation evidence was preserved — quoted directly in this
  document from either already-committed source reports or freshly
  captured output.
- [x] False positives were considered — see "Human-vs-analyzer
  classification comparison" and "Generic detection feasibility".
- [x] Recurrence was measured honestly — see "Recurrence measurement",
  including the explicit non-claim of statistical significance.
- [x] Investigation document is under `pilot/investigations/`.
- [x] Working tree contains only intended investigation material (this
  document; no source, test, or workflow files modified).
- [x] No product PR has been opened.
