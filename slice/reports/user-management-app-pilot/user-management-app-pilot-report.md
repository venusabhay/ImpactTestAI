# ImpactTestAI Pilot Report — `user-management-app`

**Tool version:** `0.2.0-pilot` **Policy version:** `repo-plus-ci-plus-cross-service-v4` (unmodified — engineering did not adapt the analyzer for this repository before or during this experiment)
**Target repository:** `/Users/abhay/git-venusabhay/user-management-app` (`venusabhay/user-management-app`), single commit (`First-commit`) on `main`. No history existed to draw real past changes from, so three isolated local experiment branches were created for analysis (not pushed): `experiment/change-a-api-cache`, `experiment/change-b-frontend-validation`, `experiment/change-c-cross-component-contract`.

---

## Executive Summary

**No — not in its current form.** Across all three real changes tested, the analyzer produced an empty impact assessment, an empty evidence list, no recommended validation, and no executed validation — including for a change that introduces a genuine, serious frontend/backend contract break. In every case it correctly avoided fabricating a probability and correctly refused to approve a change it couldn't validate (`ESCALATE`), which is the one safety property that held up. But the report text itself contains confidently-worded, specific claims that are factually false for this repository (see *Dangerous Confidence*), and the most dangerous of the three changes received the identical bland "LOW risk" verdict as the most trivial one. The root cause is structural, not incidental: nearly every discovery mechanism in the analyzer — route detection, service identification, caller/dependency detection, CI-history lookup, validation selection — is keyed off assumptions specific to `social-media-mini`'s layout (`services/<name>/` directories, `app.METHOD(...)` route syntax) that this repository does not share. The decision-safety layer (never fabricate, never silently approve) generalizes; the architecture-discovery layer underneath it does not.

## Repository Architecture

```
user-management-app/
├── docker-compose.yml          # top-level services: mongo, backend, frontend
├── user-management-api/        # single monolithic Express API (not "services/<name>/")
│   ├── server.js                # defines the app, mounts routes, exports {app, server}
│   ├── routes/userRoutes.js      # ALL endpoints defined here via express.Router(), not app.METHOD()
│   ├── controllers/userController.js  # present but unused — userRoutes.js has the actual logic inline
│   ├── middleware/authMiddleware.js   # protect() + authorize() — auth is in-process middleware,
│   │                                    not a separate service reached over HTTP
│   ├── models/userModel.js
│   ├── utils/generateToken.js
│   ├── config/db.js
│   └── __test__/user.test.js    # imports the REAL app: `import { app, server } from "../server.js"`
└── user-management-frontend/   # React + Vite SPA
    ├── src/pages/{Login,Register,Dashboard,AdminPanel}.jsx
    ├── src/components/ProtectedRoute.jsx   # decodes the JWT client-side to gate routes
    ├── src/utils/api.js         # fetch()-based client, NOT axios; handles 401 → refresh → retry
    └── (no test framework configured at all — no jest/vitest, no "test" script)
```

Key architectural facts, verified from the repository itself:

- **No `services/<name>/` layout.** Two top-level components, `user-management-api/` and `user-management-frontend/`, live directly at the repo root.
- **Routes use `express.Router()` + `router.METHOD(...)`, never `app.METHOD(...)`.** `server.js` itself only defines one route with `app.` syntax — the `/` health check. Every real endpoint (`/register`, `/login`, `/refresh`, `/profile`, `/`, `/:id/role`, `/:id`, `/logout`) is defined in `userRoutes.js` via `router.post/get/patch/delete(...)`.
- **Authentication is in-process middleware (`protect`/`authorize` in `authMiddleware.js`), not a separate service.** There is no analogue to social-media-mini's `auth-service` reached over HTTP — JWT verification happens inline, in the same process, for every request.
- **The frontend calls the backend with `fetch()`, not `axios`.** `api.js`'s `apiRequest()` wraps `fetch`, including a 401 → call `/api/users/refresh` → retry pattern.
- **The existing backend test suite genuinely imports the real application** (`import { app, server } from "../server.js"`) and drives it via `supertest` — the opposite of social-media-mini's shadow-duplicate pattern.
- **The frontend has no test framework configured at all** — no `jest`/`vitest` dependency, no `"test"` script in `package.json`.
- **No CI configuration exists** (`.github/` is absent).
- **A pre-existing, unrelated bug was noticed in passing** (not introduced by this experiment, not fixed): `/refresh` reads `req.cookies.jwt_refresh`, but `server.js` never registers `cookie-parser` — `req.cookies` would be `undefined` at runtime. Documented here as ground truth about the target repository, not acted upon.

## Test Cases

| ID | File(s) changed | Category | Description |
| --- | --- | --- | --- |
| A | `user-management-api/middleware/authMiddleware.js` | API/backend | Added a 5-second in-memory cache to `protect()`, mirroring the social-media-mini demonstration change, for direct cross-repo comparability. |
| B | `user-management-frontend/src/pages/Register.jsx` | Frontend | Added client-side password-confirmation validation (new form field + a pre-submit check). No backend contract change. |
| C | `user-management-api/routes/userRoutes.js` | Cross-component | Changed `/refresh` to read the refresh token from the `Authorization` header instead of the `jwt_refresh` cookie. The frontend (`api.js`) was **not** changed — it still calls `/refresh` via `credentials: "include"` and sends no Authorization header on that call. This breaks the token-refresh flow end-to-end. |

Each change was analyzed with: `python3 analyze_change.py <repo> --against main --github-repo venusabhay/user-management-app --npm-install`. Raw output for all three is preserved alongside this report: `change-a-api-cache-report.{md,audit.json}`, `change-b-frontend-validation-report.{md,audit.json}`, `change-c-cross-component-report.{md,audit.json}`.

## Analyzer Results

All three runs produced the same shape of result:

| | Change A | Change B | Change C |
| --- | --- | --- | --- |
| CHANGE | "no route-level change detected" | "no route-level change detected" | "no route-level change detected" |
| POTENTIAL IMPACT | *(empty)* | *(empty)* | *(empty)* |
| EVIDENCE | *(empty)* | *(empty)* | *(empty)* |
| RISK | LOW / LOW, confidence LOW | LOW / LOW, confidence LOW | LOW / LOW, confidence LOW |
| Risk indicators | `introduces new in-memory state`, `introduces or touches caching` | *(none)* | *(none)* |
| CI history | "Not collected... (no `--github-repo` provided)" — **false**, it was provided | same false message | same false message |
| Recommended validation | *(empty)* | *(empty)* | *(empty)* |
| Validation result | "No validation was executed." | same | same |
| Final decision | `ESCALATE` — "Validation could not be completed" | same | same |

No crashes, no exceptions, no non-zero exit codes. Every run produced a syntactically valid Markdown report and a valid, parseable audit JSON. `probability` was `UNKNOWN` in every case, never a fabricated bucket.

## Ground Truth

### Change A — API cache in `authMiddleware.js`

| Analyzer claim | Engineering reality | Correct? | Evidence |
| --- | --- | --- | --- |
| No route-level change detected | True in the narrow sense (no `app.METHOD` line changed) but misleading — this change alters the authentication path used by **every** `protect`-gated route: `/profile`, `GET /`, `PATCH /:id/role`, `DELETE /:id` | Partially | `authMiddleware.js` `protect` is imported and used in `userRoutes.js` lines 91, 96, 102, 117 |
| Affected component: none reported | Actual: `authMiddleware.js`'s `protect()`, used by 4 of 8 endpoints | No | grep for `protect` in `userRoutes.js` |
| Dependency: none reported | Actual: every admin/profile route depends on this middleware | No | same |
| Test coverage: "does not import the changed module" | Actual: `__test__/user.test.js` imports the real `server.js` app and exercises `/profile`, `GET /api/users`, `PATCH /:id/role`, `DELETE /:id` — all of which go through `protect()` | **No — the claim itself was never evaluated; it's boilerplate text from a code path that never ran** | `user.test.js` line 2: `import { app, server } from "../server.js"` |
| Risk indicators: caching / new state | Correct — the diff does add `new Map()` and cache logic | Yes | diff itself |
| Risk level: LOW | Actual: at minimum MEDIUM — this is the same class of staleness/authorization-bypass risk found and confirmed in the social-media-mini pilot, here affecting more of the API's own endpoints than social-media-mini's `/verify` affected sibling services | No | see Stage 2B finding in the design8/9 vertical slice; identical code pattern here |
| Recommended validation: none | Actual: `npm test` in `user-management-api` exists, is real, and (per ground truth above) already exercises the changed path indirectly through `/profile` etc. | No | `user-management-api/package.json` has a working `"test"` script |
| Final decision: `ESCALATE` (no validation available) | Directionally defensible (nothing ran) but for the wrong reason — validation exists and wasn't found, not "unavailable" | Partially | see above |

### Change B — frontend password-confirmation validation

| Analyzer claim | Engineering reality | Correct? | Evidence |
| --- | --- | --- | --- |
| No route-level change detected | Correct — this is a pure UI change with no backend implication | Yes | diff is confined to `Register.jsx` |
| Affected component: none | Actual: `Register.jsx`'s submit handler only | Yes (trivially, nothing else is affected) | diff |
| Risk indicators: none | Correct — no risky pattern present | Yes | diff |
| Risk level: LOW | Correct | Yes | this is genuinely a low-risk change |
| Test coverage: "does not import the changed module" | **False as stated** — no test file was found or examined at all; the frontend has zero test infrastructure, so the claim of a specific test file's behavior is fabricated boilerplate, not an evaluated fact | No | `user-management-frontend/package.json` has no `"test"` script and no test dependency |
| Recommended validation: none | Correct outcome, right reason this time — there genuinely is nothing to run | Yes | same |
| Final decision: `ESCALATE` | Arguably overcautious for a change this size, but not wrong given zero test infrastructure exists | Yes (defensible) | same |

### Change C — cross-component contract break (`/refresh`)

| Analyzer claim | Engineering reality | Correct? | Evidence |
| --- | --- | --- | --- |
| No route-level change detected | **Wrong in the way that matters most** — a real endpoint (`GET /refresh`) had its request contract changed | No | `userRoutes.js` diff, `router.get("/refresh", ...)` |
| Affected component: none | Actual: the entire frontend token-refresh flow | No | `api.js` lines 14–29 call this exact endpoint |
| Dependency: none | Actual: `user-management-frontend/src/utils/api.js` depends on `/api/users/refresh`'s cookie-based contract; that dependency is now broken | **No — this is exactly the class of dependency the tool's caller-detection mechanism is built to find, and it found nothing** | literal string `/api/users/refresh` appears in `api.js`; never surfaced |
| Risk indicators: none | Actual: this change silently breaks every user's session-refresh behavior — every 401 will now fail to recover, forcing an unexpected logout | No | frontend still calls without an `Authorization` header on this request; backend no longer reads the cookie |
| Risk level: LOW | **Wrong, and dangerously so** — ground truth is at least MEDIUM-HIGH: guaranteed, silent, 100%-reproducible break of an authentication flow, indistinguishable in the report from Change B's harmless UI tweak | No | reasoning above |
| CI history: "not collected (no `--github-repo` provided)" | **False as stated** — `--github-repo` was passed; history was never fetched because no service name could be derived, not because the flag was missing | No | audit JSON: `ci_history: {}` despite the flag being present in the command |
| Recommended validation: none | Actual: a real integration test exists (`user.test.js`) that could be extended to catch exactly this — but nothing was recommended | No | same test-import fact as Change A |
| Final decision: `ESCALATE` | Same bland verdict as Change B | Correct verdict, indistinguishable reasoning from a trivial change — a human reading only the two reports could not tell these apart | see side-by-side table above |

## Accuracy

| Category | Count | Notes |
| --- | --- | --- |
| Correct findings | 5 | No crash on any run; `probability` never fabricated in any run; Change B's risk level (LOW) and empty indicators were correct; the "no validation ran" fact was literally true in all three cases; final `ESCALATE` never silently approved anything |
| Incorrect findings | 9 | All three "no route-level change" framings undersell what changed; all three "test file does not import the changed module" claims are unevaluated boilerplate, one of which (Change A) is factually backwards; all three "CI history not collected (flag not provided)" messages are false; Change A and C's risk levels are both wrong (should be MEDIUM+ and MEDIUM-HIGH+ respectively); Change C's complete silence on the broken frontend/backend contract |
| Unknown / not testable | 1 | Whether a hypothetical, purpose-built cross-service test would be *executed* correctly if one existed — not tested here per the task's explicit instruction not to build a generalized integration-testing capability; determined by code inspection instead (see Validation Capability) |

## Validation Capability

**Nothing was executed in any of the three cases**, despite `user-management-api` having a real, working `npm test` (confirmed manually: `cross-env NODE_OPTIONS=--experimental-vm-modules jest --runInBand --coverage`, using `supertest` against the real app). The reason, traced through the code rather than assumed:

`build_validation_decision()` computes `services = {service_name_from_path(p) for p in changed_files if service_name_from_path(p)}`, and `service_name_from_path()` matches only the pattern `services/([^/]+)/`. No file in this repository matches that pattern (paths look like `user-management-api/routes/userRoutes.js`), so `services` is empty for every change, the per-service `npm test` selection loop never executes, and `selected_validations` is `[]` regardless of what changed or how risky it was.

**Cross-service validation specifically:** the same root cause means it could not be assessed even in principle. `caller_services` (used to decide whether an `E2E_TEST` validation is offered) is derived from `find_callers()`, which discards any match whose `service_name_from_path()` is falsy — always true here. Per the task's instruction not to build a generalized integration-testing framework for this experiment, no new cross-service test was authored; the conclusion above is established directly from the code path, not inferred from a missing attempt, and is corroborated by all three real runs showing `structural_exposure.caller_services: []`.

## Architecture Limitation

Every failure traced above has the same two root causes, both `services/<name>/`-era assumptions baked into `analyze_change.py`:

1. **`service_name_from_path()`** hardcodes the regex `services/([^/]+)/`. This repository's top-level components (`user-management-api/`, `user-management-frontend/`) never match it, so every mechanism keyed on "which service does this file belong to" — test-coverage matching, caller/dependency detection, CI-history lookup, validation selection — silently returns nothing.
2. **`find_route_handlers()`** matches only the literal pattern `app.(get|post|put|delete|patch)(...)`. This repository defines every real endpoint via `express.Router()` + `router.METHOD(...)`, which never matches, so route-level impact detection returns nothing for the one file where it matters most (`userRoutes.js`).

Both are architecture-*discovery* assumptions, not decision-*policy* assumptions. The parts of the tool that don't depend on discovering "which service" or "which route" — diff-text pattern scanning (`scan_risk_patterns`), the refusal to fabricate probability, the refusal to approve when nothing validated — worked identically to how they worked on social-media-mini.

## False Positives

None in the sense of "confidently flagged something that wasn't actually a problem." The closest analogue is structural: reporting `RISK: LOW` is not technically a false claim about a *nonexistent* risk, but combined with zero identified impact and zero recommended validation, a reader could reasonably take the report as "this is fine" — which, for Change C, it explicitly is not.

## False Negatives

- **Change A**: real test coverage of the changed authentication path exists (`user.test.js`, via `/profile`, admin routes) and was not recommended or run.
- **Change C**: the frontend's dependency on `/refresh`'s cookie-based contract exists in the code (`api.js`), is a real, literal, greppable fact, and was not detected — this is the most consequential false negative in the experiment, since it is precisely the "cross-component dependency" category the tool exists to catch.

## Dangerous Confidence

Three concrete instances, all worse than a plain "I don't know":

1. **Change A's WHY text**: *"The relevant existing test file does not import the changed module."* This is stated as an evaluated fact. It was never evaluated — the code path that would have checked it never ran, because no route handler was found in the changed file. The actual answer (a real test file does import the real app) is the opposite of what's implied.
2. **All three runs' CI-history line**: *"Not collected for this run (no `--github-repo` provided)."* False in all three cases — the flag was explicitly passed on the command line (verified in the exact commands run for this report). The real reason (no service could be derived) is silently substituted with a plausible-sounding but incorrect one.
3. **Change C rated identically to Change B.** A guaranteed, 100%-reproducible break of the authentication-refresh flow and a cosmetic form-validation tweak produced byte-for-byte identical `RISK`/`WHY`/`DECISION` sections (differing only in the diffstat). A reader relying on this report has no way to distinguish the two without already knowing the codebase — which defeats the purpose of the tool.

## Reusable Capabilities

Worked without any modification, on this different architecture:

- Git diff/ref mechanics (`get_change`, line-range parsing) — computed correctly regardless of repo layout.
- `scan_risk_patterns()` — diff-text keyword scanning is repo-layout-agnostic; it correctly fired for Change A's cache/state pattern.
- The "probability stays `UNKNOWN`, never fabricated" invariant — held in all three runs, unconditionally, exactly as designed.
- The "no validation ran → `ESCALATE`, never silently proceed" safety default — held in all three runs. Even in total discovery failure, the tool never told anyone a change was safe. This is the one property that most directly protects the business from the discovery layer's failures, and it worked.
- Overall execution robustness — no crashes, valid Markdown and JSON output every time, `--npm-install` correctly installed real dependencies in `user-management-api` with no manual setup.

## Comparison to `social-media-mini`

| Capability | social-media-mini (`services/auth-service/`...) | user-management-app | Depends on `services/<name>` layout? |
| --- | --- | --- | --- |
| Diff/change capture | Worked | Worked | No |
| Diff-text risk-pattern scanning | Worked | Worked (fired correctly for Change A) | No |
| `probability` stays `UNKNOWN`, never fabricated | Held | Held | No |
| Route/endpoint detection | Worked (`app.post("/verify", ...)`) | **Failed** (`router.post(...)`, never matched) | No — this depends on Express calling-convention detection, a separate, narrower assumption than the directory layout |
| Service/component identification | Worked (`services/auth-service/`) | **Failed** (no `services/` prefix exists) | **Yes** |
| Cross-service dependency detection | Worked (found `post-service`/`user-service` calling `/verify`) | **Failed** (frontend's real dependency on `/refresh` never found) | Yes — gated behind service identification succeeding first |
| Test-coverage evidence (import-detection) | Worked, and drove a correct, valuable low-confidence finding | **Produced a false claim** (said a test doesn't import the module without ever checking) | No — this is a distinct bug (unconditional boilerplate text), not a services/ dependency |
| CI-history fetch | Worked | **Silently skipped**, with a false explanatory message | Yes — gated behind service identification succeeding first |
| Validation selection (`npm test` per service) | Worked | **Failed** (empty service list → nothing selected) | **Yes** |
| "No validation → `ESCALATE`" safety default | Held | Held | No |

**Answer to the two questions this experiment was asked to settle:** the safety/decision properties (no fabrication, no silent approval, correct diff/pattern mechanics) continue to work unchanged. Everything that requires knowing *which component* a file belongs to — validation selection, cross-component dependency detection, CI-history lookup — depends entirely on the `services/<name>` assumption and fails completely without it. Route/endpoint detection and the truthfulness of explanatory text are separate, narrower bugs, not consequences of the directory-layout assumption, and would need fixing even in a `services/<name>`-shaped repo that happened to use `express.Router()`.

## Required Product Changes

Only what this experiment actually justifies — no redesign, no new architecture:

1. **Route detection must recognize `express.Router()` + `router.METHOD(...)`, not only `app.METHOD(...)`.** Justified directly: this single gap caused every "no route-level change detected" result in this experiment.
2. **Service/component identification must not hardcode `services/<name>/`.** Justified directly: this single gap caused every empty impact assessment, every empty validation selection, and every silently-skipped CI-history fetch in this experiment.
3. **Boilerplate explanatory text must not be emitted for a check that never ran.** Justified directly by two independently-observed false statements (the test-import claim and the CI-history claim) in this experiment. This is a truthfulness fix, not a capability expansion — the fix is to say `UNKNOWN` or omit the line, not to make the underlying check smarter.

Explicitly not justified by this experiment: generalized multi-layout architecture discovery, a plugin system for route frameworks, or any change to the risk/decision algorithm itself — the decision layer's behavior was correct given its inputs; the inputs were empty.

## Usefulness Scores

0 = unusable, 1 = mostly wrong, 2 = partially useful, 3 = useful with engineering review, 4 = very useful, 5 = production-quality.

| Dimension | Change A (API cache) | Change B (frontend) | Change C (cross-component) | Basis |
| --- | --- | --- | --- | --- |
| Change identification | 2 | 3 | 1 | Files/diffstat always correct; "no route-level change" framing is misleading for A, actively wrong for C |
| Impact identification | 0 | 1 | 0 | Empty in all three; B's empty result happens to be correct but for reasons unrelated to real analysis |
| Dependency identification | 0 | 2 | 0 | Missed 4 real dependent routes (A) and the frontend's real dependency on `/refresh` (C); B genuinely has none to find |
| Risk assessment | 1 | 4 | 0 | A's indicators fired but risk level too low; B correctly calibrated; C is the dangerous-confidence case |
| Test discovery | 0 | 1 | 0 | A: false claim, real coverage existed; B: unevaluated boilerplate; C: same false claim, relevant test existed |
| Validation recommendation | 0 | 1 | 0 | Nothing recommended in any case; B's "nothing to recommend" happens to be correct |
| Validation execution | 0 | 0 | 0 | Nothing executed in any case — no differentiation possible |
| Final decision usefulness | 2 | 3 | 1 | `ESCALATE` is a safe non-committal default throughout; indistinguishable between B and C undermines its usefulness for C specifically |

**Overall reading:** the tool never crossed into "useful with engineering review" (3+) on more than isolated dimensions, and its one genuinely correct set of scores (Change B) reflects a change simple enough that an empty, cautious report was directionally harmless — not evidence the tool actually analyzed it. Change C, the case that mattered most, scored at or near zero on every dimension that isn't a safety default.

## Recommendation

**`ADAPT_ARCHITECTURE_DISCOVERY`**

The reasoning chain proven on social-media-mini (impact → risk → validation → real outcome → honest escalation) is sound and its safety properties generalize across architectures — confirmed here by the fact that even total discovery failure never produced a false "proceed." But the discovery layer beneath that chain is narrowly built for one repository's conventions, and on a differently-shaped real repository it produced no usable signal on three separate real changes, plus three specific, verifiable false statements. Handing this to another engineering team today, unmodified, would not help them make a better validation decision — for the one change that mattered most (Change C), it would actively mislead them into thinking a form-tweak and an authentication-flow break carry the same risk. The three required changes above are narrow, are each directly evidenced by this experiment, and do not require touching the risk/decision policy that Stage 1/2/2B already validated.
