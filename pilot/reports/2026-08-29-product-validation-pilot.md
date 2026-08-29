# Product Validation Pilot — 2026-08-29

**Objective:** does ImpactTestAI, as it exists today, provide useful
and trustworthy impact discovery and validation evidence to a pilot
user? Scored against the acceptance contract in
[`docs/PRODUCT_VALIDATION_SPEC.md`](../../docs/PRODUCT_VALIDATION_SPEC.md).

**Not an investigation.** No product behavior was changed to produce
this round. `TOOL_VERSION`/`POLICY_VERSION` unchanged
(`0.10.0-pilot`/`repo-plus-ci-plus-cross-service-plus-discovery-v9`
throughout). 113/113 tests pass, confirmed before and after this round.
Every case below used the analyzer exactly as a pilot user would invoke
it (`--npm-install`, optionally `--github-repo`); the one exception —
re-running Case 5 with `--validation-timeout-seconds 600` — used an
existing, documented, sanctioned CLI flag, not a new capability.

## Sample and selection rationale

5 real repositories/commits, **none used in any prior investigation or
pilot round in this project.** Selected for structural variety before
their outcomes were known — none was chosen because a particular result
was expected or desired, and none was modified to produce a particular
outcome.

| # | Repository | Real commit | Why selected |
|---|---|---|---|
| 1 | `expressjs/cors` | `01477dc` — "Fix setting maxAge option to 0" (2018) | Small, focused, real bug fix with its own accompanying test — the "small, straightforward change" case |
| 2 | `w3cj/express-api-starter` | `0f9e38d` — "upgrade to modules and express v5" | A real, substantial service/API migration (CommonJS→ESM, Express 4→5) touching real registered routes |
| 3 | `socketio/socket.io` (`packages/socket.io-parser`) | `7c6ef571` — "reject binary packets with zero attachments" | A real, focused fix to a shared package other packages in the same monorepo depend on — the "cross-service" case |
| 4 | `expressjs/express` | `18e5985b` — "add Content-Length header only if Transfer-Encoding is not present" | An established, heavily-tested framework core with real, matching CI history — the "meaningful CI history" / clean-suite case |
| 5 | `fastify/fastify` | `af079bd4` — "disable numeric trustProxy hop-count trust" | A real, security-relevant fix with a large accompanying test update, in another large established suite |

No case was manufactured to produce a failure. Two cases (3 and 5)
happened to surface real friction on their own — that is reported as
evidence, not engineered.

An eighth planned dimension — "a change with meaningful CI history"
via successful, complete retrieval — was **not achievable within this
round's real constraints**: every actively-maintained repository
sampled (`cors`, `serve-static`, `express`) has 90+ real workflow runs
in its recent-100 window (CodeQL, dependabot, matrix jobs), and a full
CI-history fetch for one of those costs 90+ GitHub API calls against
the unauthenticated 60-requests/hour ceiling. This is itself reported
below as a real, repeated finding, not glossed over.

## Per-case results

### Case 1 — `expressjs/cors`, `01477dc`

- **Human expectation:** `cors` is a middleware *library*, not a routed
  application — no route-level impact should exist. The fix
  (`lib/index.js`, `configureMaxAge`) has its own new test
  (`test/test.js`); a clean pass is expected.
- **Discovered:** correctly attributed both changed files to the `cors`
  component. Correctly found **zero** route/middleware relationship —
  honestly disclosed via `IMPORTANT UNKNOWNS`, not silently treated as
  no-impact.
- **Correct / incomplete / overly broad:** correct — there is genuinely
  no route-registration convention in this repository for discovery to
  find.
- **Validation executed:** yes, real `npm test`.
- **Validation result truthful:** yes — `PASSED`, 49 tests, including
  the exact `"includes maxAge when specified and equals to zero"` test
  covering this fix.
- **CI/history evidence useful:** **partially.** 94 real workflow runs
  correctly discovered in-window (confirming 0.10.0's generic-path fix
  works here), but almost every per-run job-detail fetch hit
  `HTTP Error 403: rate limit exceeded` — honestly reported as
  limitations, not fabricated as either a clean or a failing history.
  Real, but not practically usable in this environment.
- **Recommendation understandable/conservative:** yes —
  `REQUIRE_ADDITIONAL_VALIDATION`, reason cited directly (`overall
  confidence is LOW`).
- **What a human would do differently:** likely nothing — a human
  reading this diff and its test would merge without hesitation; the
  tool's caution here adds no real incremental signal over what's
  already obvious from the diff.

### Case 2 — `w3cj/express-api-starter`, `0f9e38d`

- **Human expectation:** a real migration touching all three of this
  app's actual routes: `GET /` (`src/app.js`), `GET /api/v1`
  (`src/api/index.js`, mounted at `/api/v1`), and `GET /api/v1/emojis`
  (`src/api/emojis.js`, mounted at `/emojis` under the `/api/v1`
  router). Real tests (`test/app.test.js`, `test/api.test.js`) both
  `import app from "../src/app.js"` and exercise all three.
- **Discovered:** correctly found all three routes as directly
  impacted — but **labeled all three identically as `GET /`**, with no
  indication they are three different real endpoints.
- **Correct / incomplete / overly broad:** the *count* and *component*
  are correct; the *presentation* is misleading — a reviewer skimming
  `## POTENTIAL IMPACT` could reasonably believe there is one changed
  route, not three.
- **Validation executed:** yes, real `vitest run`.
- **Validation result truthful:** yes — 4/4 tests genuinely passed.
- **CI/history evidence useful:** N/A — this repository genuinely has
  **zero** GitHub Actions runs, ever. Correctly, honestly reported as
  absent (`runs examined: 0`), not as "could not retrieve."
- **Recommendation understandable/conservative:** yes —
  `REQUIRE_ADDITIONAL_VALIDATION`, reasonable for a major-version
  migration.
- **What a human would do differently:** would immediately recognize
  three distinct endpoints from reading the diff and weight risk
  per-endpoint — something the report's flattened presentation doesn't
  support without cross-checking the actual source.
- **A second, related finding:** `## IMPORTANT UNKNOWNS` states *"No
  test file evidence found for GET /"* — despite both real test files
  genuinely importing and exercising `app.js`. Root cause: the
  test-coverage check searches for a literal reference to the route's
  recorded path string (`"/"`), but the tests correctly call the
  *composed* real URLs (`/api/v1`, `/what-is-this-even`), which never
  contain the bare, uncomposed `"/"` substring discovery recorded. This
  is the same underlying limitation as the labeling issue above (route
  paths are recorded as the literal per-file string, without composing
  `app.use(prefix, router)` mount prefixes) — one root cause, two
  visible symptoms in the same real report.

### Case 3 — `socketio/socket.io` (`packages/socket.io-parser`), `7c6ef571`

- **Human expectation:** a small, real, security-relevant fix (rejects
  malformed binary packets) with its own new test in
  `test/parser.js`; running that package's own `npm test` should
  validate it.
- **Discovered:** correctly identified `socket.io-parser` as the
  affected component within a real monorepo (package.json-based
  discovery working correctly here). Correctly found zero route/
  middleware relationship (a parser library has no routes).
- **Validation executed:** attempted, but never reached the real test
  suite — `npm install`, scoped to
  `packages/socket.io-parser/` alone, produced a
  package lacking `prettier` (a devDependency this Yarn/npm-workspaces
  monorepo hoists to the *root* `node_modules`, not the sub-package's
  own). The test script's first step, `format:check`, failed at
  `sh: prettier: command not found` (exit 127) before any real test
  ran.
- **Validation result truthful:** technically yes — `FAILED`, exit
  127, real stderr, honestly reported, classification correctly says
  `Unknown / insufficient evidence -- requires human triage`.
  **Practically misleading:** a pilot user skimming `FAILED`/`ESCALATE`
  would reasonably suspect the change broke something; the real cause
  is a mismatch between this analyzer's per-component `npm install`
  model and this repository's monorepo workspace structure.
- **CI/history evidence:** not requested for this case (rate-limit
  budget management, see above).
- **Recommendation understandable/conservative:** technically correct
  per policy (any `FAILED` forces `ESCALATE`) but **this is exactly the
  class of ambiguous, environment-caused failure the
  environment-failure-classification investigation examined and
  deferred on** — independently reconfirmed here, live, in a
  completely different, fresh repository never used in that
  investigation.
- **What a human would do differently:** immediately recognize
  `"prettier: command not found"` as a tooling/environment issue
  unrelated to the code change, and manually re-run with a
  workspace-aware install to get a real answer.

### Case 4 — `expressjs/express`, `18e5985b`

- **Human expectation:** a small, well-tested internal fix to the
  framework's own `res.send()`; framework internals aren't routes, so
  no route-level impact is expected; the large, established suite
  should pass.
- **Discovered:** correctly found zero route/middleware relationship
  (honest — `lib/response.js` isn't a routed app). Correctly selected
  and ran `npm test`.
- **Validation executed and truthful:** yes — **1258 tests, all
  genuinely passing**, including the new test added alongside this
  exact fix.
- **CI/history evidence:** not requested this round, to conserve API
  budget (already separately confirmed correct in the 0.10.0
  CI-workflow-discovery milestone).
- **Recommendation understandable/conservative:** yes —
  `REQUIRE_ADDITIONAL_VALIDATION`, same LOW-confidence floor as every
  case in this project to date.
- **What a human would do differently:** would likely accept this
  change on the passing suite alone; for a change this narrow and this
  well-tested, the blanket confidence ceiling adds limited incremental
  signal — the same observation as Case 1.

### Case 5 — `fastify/fastify`, `af079bd4`

- **Human expectation:** a real, security-relevant fix (trust-proxy /
  hop-count handling — a classic IP-spoofing-adjacent concern) with a
  large accompanying test update (48 lines); framework internals, no
  routes expected; a large, established suite.
- **Discovered:** correctly zero route/middleware relationship
  (honest). Correctly selected `npm test`.
- **Validation executed — first attempt:** hit the **default 180s
  timeout** → `INCONCLUSIVE`, `INFRASTRUCTURE (timeout)`, `ESCALATE` —
  exactly as designed: no crash, no fabrication, no silent retry.
- **Validation executed — re-run with `--validation-timeout-seconds
  600`** (an existing, documented flag, used exactly as `PILOT.md`
  itself instructs for this situation): completed in **71.3 seconds**,
  **1279 assertions, all passing.**
- **Validation result truthful:** yes, both times — an honest timeout,
  then an honest pass.
- **Interpretation:** the original 180s timeout most likely reflects a
  one-time cold-start cost (first-time dependency install/build inside
  this run), not evidence that fastify's suite is inherently slower
  than 180s — a materially different, more precise finding than the
  earlier Archify case (which genuinely needed ~338s on repeat runs).
  Worth stating distinctly rather than treating every timeout as the
  same shape.
- **Recommendation understandable/conservative:** yes.
- **What a human would do differently: nothing — this is the system
  working exactly as intended.** `PILOT.md`'s own guidance ("if you
  keep seeing ESCALATE with a timeout classification and you're
  confident your suite is healthy, that's the signal to raise this
  value") describes precisely this sequence, and following it produced
  a clean, correct, fast result.

## Six-criterion scorecard

Per [`docs/PRODUCT_VALIDATION_SPEC.md`](../../docs/PRODUCT_VALIDATION_SPEC.md) §4, no new criteria introduced.

| # | Criterion | Case 1 (cors) | Case 2 (api-starter) | Case 3 (socket.io-parser) | Case 4 (express) | Case 5 (fastify) |
|---|---|---|---|---|---|---|
| 1 | Identified the affected component? | Pass | **Partial** (component right, 3 routes flattened to one label) | Pass | Pass | Pass |
| 2 | Validation actually exercised the relevant behavior? | Pass | Pass | **Fail** (never reached the real test) | Pass | Pass (after extending timeout) |
| 3 | Avoided claiming evidence it didn't have? | Pass | **Partial** (under-credited real, passing test coverage — a false negative, not a fabrication) | Pass | Pass | Pass |
| 4 | Surfaced a genuine regression? | N/A (none present) | N/A (none present) | N/A (none present) | N/A (none present) | N/A (none present) |
| 5 | Avoided unnecessary escalation? | **Partial** (arguably excessive caution on a trivial, well-tested fix) | Pass (reasonable for a major migration) | **Fail** (escalation driven by a tooling artifact, not the change) | **Partial** (same as Case 1) | Pass (escalate-then-resolve is the intended flow) |
| 6 | Human reviewer could understand the recommendation? | Pass | Pass | Pass | Pass | Pass |

No case in this round contained a genuine, independently-verifiable
regression (criterion 4 is `N/A` throughout) — consistent with "do not
manufacture failures": none was sought or engineered.

## False positives

**None demonstrated in this round.** The closest analog is Case 2's
route-flattening, but that under-differentiates real impact (three
routes look like one) rather than over-claiming impact that doesn't
exist — the opposite direction from a classic false positive, and
worth naming precisely rather than lumping in with one.

## False negatives

- **Case 2:** real, passing, directly-relevant test coverage
  (`app.test.js`/`api.test.js`, both genuinely importing and exercising
  `app.js`) was not credited as `TEST_COVERAGE` evidence for the `GET
  /` route, because the coverage check matches on the route's
  literal, uncomposed path string rather than the composed URL the
  tests actually request. Confirmed, not merely suspected — the
  test files were read directly.

## Cases where evidence was insufficient

- **Case 1:** CI history was real and substantial (94 runs) but mostly
  unretrievable due to the GitHub API's unauthenticated rate limit —
  correctly reported as `limitations`, not fabricated.
- **Case 2:** CI history genuinely does not exist for this repository —
  correctly distinguished from "could not retrieve."
- **Case 3:** validation could not produce a real result at all, due to
  a monorepo/workspace install-scoping mismatch — correctly reported
  as `FAILED`/`ESCALATE` with full raw evidence, but without any
  attempt to diagnose *why*, consistent with the existing product
  contract's explicit non-promise on ambiguous environment failures.

## Cases where the product appropriately refused to guess

- Every case's zero-route-relationship files (Cases 1, 3, 4, 5) were
  disclosed as explicit `IMPORTANT UNKNOWNS` rather than silently
  treated as zero-impact.
- Case 3's `FAILED` result carried an explicit `classification: Unknown
  / insufficient evidence -- requires human triage` rather than a
  guessed cause — even though the raw evidence (`prettier: command not
  found`) would have been easy to misclassify with a naive heuristic.
- Case 2's absent CI history was reported as `runs examined: 0`, not
  conflated with Case 1's rate-limited-and-therefore-unknown history —
  the product contract's promised distinction held up under real,
  fresh conditions.

## User-impact assessment

In every one of the 5 cases, a pilot user would have received **truthful, non-fabricated evidence** — the tool never presented more
confidence than the evidence supported, and every escalation was
traceable to a real, cited fact. The two concrete friction points found
(Case 2's route-label flattening/under-credited coverage; Case 3's
monorepo-install-scoping false-`FAILED`) would each cost a user a few
minutes of manual cross-checking against the actual diff or a manual
re-run — real friction, but not a case of the tool actively misleading
someone toward a wrong decision. The worst realistic outcome across
this round is "confusing, requires a second look," not "confidently
wrong." Case 5 additionally demonstrates the product working exactly
as designed end-to-end, including the documented recovery path for a
slow-but-healthy suite.

## Overall verdict

**READY WITH KNOWN LIMITATIONS**

The tool was safe and honest in all 5 fresh, real, unmanufactured
cases: zero fabricated evidence, zero false confidence, every
escalation traceable to a real fact, and every "insufficient evidence"
state correctly and distinctly labeled (rate-limited vs. absent vs.
uninvestigable). That is the core trustworthiness bar in
`docs/PRODUCT_VALIDATION_SPEC.md`, and it held under fresh, real
conditions with no cases selected or altered to make it hold.

It is not an unconditional `READY`, because this round surfaced two
concrete, reproducible limitations beyond what was previously
documented, both consistent with — not contradicting — the product's
existing non-promises:

1. **Route-path presentation is not composed across mount prefixes**
   (Case 2) — a real evidence-quality gap (both under-differentiated
   impact labeling and under-credited test coverage) distinct from,
   though related to, the already-documented whole-file-granularity
   limitation.
2. **Per-component `npm install` does not account for monorepo/
   workspace-hoisted dependencies** (Case 3) — a real, reproducible way
   for a genuinely-unrelated environment mismatch to produce a
   plain `FAILED`/`ESCALATE` result indistinguishable, without human
   investigation, from a real regression.

Neither is a safety failure — nothing was ever presented as more
certain than the evidence supported, and both are disclosed here
plainly rather than fixed reactively, per this round's explicit
instruction not to change product behavior. Per this document's own
finding: these are exactly the kind of "gaps that actually matter"
`docs/PRODUCT_VALIDATION_SPEC.md` asked to be identified, not
implemented, from this round.

---

## Completion gate

- [x] Baseline `main` unchanged (`3f165a9`; this branch adds only this
  report).
- [x] No `.py` source changes.
- [x] No policy/risk/recommendation changes.
- [x] No `.github/workflows/` changes.
- [x] No new repository-specific behavior.
- [x] Existing tests pass — 113/113, confirmed before and after.
- [x] All 5 pilot cases are real, fresh (not used in any prior
  investigation), and reproducible (exact commit SHAs recorded above).
- [x] Raw evidence preserved — quoted directly from the actual
  generated reports throughout this document.
- [x] Generated artifacts (reports, `node_modules`, cloned repositories)
  remain uncommitted — produced under a scratch directory outside this
  repository, not under `pilot/`.
- [x] This report is committed under `pilot/reports/`.
- [x] No implementation PR opened as part of this pilot.
