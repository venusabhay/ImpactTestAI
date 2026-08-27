# ADAPT_ARCHITECTURE_DISCOVERY — Final Business Report (v7)

**Branch:** `feature/adapt-architecture-discovery` (not merged to `main`)
**Freeze commit:** `7a12b18`

---

## A. What Improved

This round was narrowly scoped, per the business owner's own milestone framing, to exactly the two gaps the v6 held-out round found on `edwinhern/express-typescript` — nothing else:

1. **Comment-blind scanning** → `discovery.strip_comments()`, a lightweight character-scanning state machine that blanks `//` and `/* */ ` comment content (respecting string/template-literal boundaries) before route/export scanning, preserving line numbers exactly. Applied at the top of `find_route_registrations()`, `find_exported_names()`, and inside `find_middleware_usages()`'s per-file scan.
2. **Class-based controller (`controller.methodName`) handlers not connected to their routes** → `discovery._resolve_arg_to_export()` resolves a middleware/handler argument against a file's exports either by exact match (bare identifier, existing behavior) or by matching the **root identifier** of a dotted property-access reference — general, because class methods are never themselves module exports in JS/TS, only the class/instance binding is. This required fixing a real underlying bug found while testing it: `_extract_middleware_args()` was not stripping a trailing `;` after a bare/dotted final-handler reference with no inline function, so such tokens never reached the identifier regex at all.

None of these changes touched `RiskAssessment` semantics, `probability` handling, `risk_level` thresholds, `RISK_PATTERNS`, `SENSITIVE_PATH_HINTS`, validation-selection policy, the `ESCALATE`/`REQUIRE_ADDITIONAL_VALIDATION`/`ACCEPT` rules, cross-service test detection, or `design8.md`/`design9.md`. Verified by inspection of every diff on the branch.

## B. Known Repositories

| Repository | Change | Recorded criterion | Result |
| --- | --- | --- | --- |
| social-media-mini | `/verify` caching (Stage 2B) | Security regression remains detectable | ✅ Reproduces identically |
| user-management-app | Change A (API caching) | Remains identifiable | ✅ `CRITICAL` risk, 4 middleware-dependent routes, `REQUIRE_ADDITIONAL_VALIDATION` |
| user-management-app | Change B (frontend validation) | Remains low-impact | ✅ `LOW` risk, empty impact, `ESCALATE` |
| user-management-app | Change C (contract break) | Remains distinguishable from B | ✅ `MEDIUM` business impact/exposure, still visibly distinct from B |
| `edwinhern/express-typescript` | Both v6-found gaps, re-verified against the exact repository that found them | Both should now resolve | ✅ `userController.ts` change now correctly produces `GET /` and `GET /:id` `MIDDLEWARE_DEPENDENCY` impact; the original comment-shaped false positive no longer fires |

All pass. Decision-policy behavior (probability always `UNKNOWN`, no validation → `ESCALATE`, thresholds) unchanged — confirmed by identical `RISK`/`DECISION` sections, differing only in the tool/policy version footer. 57/57 automated tests pass (10 new: 7 comment-awareness, 3 controller-method resolution).

## C. Held-Out Repositories

Selected only after freeze commit `7a12b18`, neither inspected before that point. `expressjs/express`, `edwinhern/express-typescript`, `ai-agents`, and `langgraph-demo` are now "known" (used to develop or verify prior rounds' fixes) and do not count as fresh evidence this round.

| Repository | Architecture | Change | Expected | Actual | Result |
| --- | --- | --- | --- | --- | --- |
| `hagopj13/node-express-boilerplate` (7.7k★, real, actively maintained; plain CommonJS, layered routes/controllers/services) | Real historical commit `750feb5` — "Add logout endpoint" (adds `POST /logout` + `POST /refresh-tokens` calls in `auth.route.js`, plus new handler code in `auth.controller.js`/`auth.service.js`/`auth.validation.js`) | Both new routes discoverable as direct impact | ✅ Both routes correctly identified (`POST /logout`, `POST /refresh-tokens`), precise line ranges, `HIGH` confidence. ❌ But: `auth.controller.js`/`auth.service.js`/`auth.validation.js` were **not** connected to the routes that call them — see Remaining Limitations #1 | ⚠️ **Partial success** — the change that touched the route file directly was caught precisely; a new, general discovery gap was found on the files that did not |
| `hagopj13/node-express-boilerplate` | Same | Real historical commit `d3d3e0f` — one-line variable rename in `bin/createNodejsApp.js` (a CLI scaffolding script, not a route file) | Low/no impact | Empty impact, `LOW` risk, `ESCALATE` (default, no validation run) — correctly flagged as an honest unknown rather than silently ignored | ✅ **Success — correct discrimination from the meaningful change above** |
| `lujakob/nestjs-realworld-example-app` (3.4k★, real, actively maintained; **NestJS**, decorator-based routing — `@Get('user')`, not `receiver.method(path, ...)`) | Real historical commit `7c7e385` — "fix: auth middleware user object", touches `auth.middleware.ts`, `user.controller.ts`, `user.decorator.ts`, `user.service.ts` | Genuinely out of scope (no Express-style calling convention anywhere in this codebase) | Empty impact, `LOW` risk, all four changed files explicitly flagged in `IMPORTANT UNKNOWNS` as possibly-out-of-scope, `ESCALATE` | ✅ **Correctly, safely out of scope** — no crash, no fabricated confidence |
| `lujakob/nestjs-realworld-example-app` | Same | Real historical commit `6df396d` — dependency bump (`package.json`/`package-lock.json`/`yarn.lock` only, no source files) | No impact, no unknowns (nothing source-level touched) | Empty impact, `LOW` risk, **zero** `IMPORTANT UNKNOWNS` entries — correctly distinct from the case above, where source files *were* touched but out of scope | ✅ **Success — correct fine-grained discrimination** |

**Note on validation execution:** the four held-out reports above were generated with `--no-run` (impact/risk/discovery analysis only, no test execution) — this round's scope is discovery, not the validation-execution engine, which is unchanged since v4. An attempt was made to also run real `npm test` validation on both repositories for completeness: `node-express-boilerplate`'s install failed under this machine's current npm due to a peer-dependency resolution conflict between its ~2020-era `eslint`/`eslint-config-airbnb-base` devDependencies and a modern npm's stricter resolver (recoverable with `--legacy-peer-deps`, still in progress as of this report); `nestjs-realworld-example-app`'s install failed with an unrelated npm-internal error ("Exit handler never called!"). Both are local tooling/environment issues, not defects in the analyzer or evidence of a code regression — consistent with previously disclosed environment issues in this project (`mongodb-memory-server` startup flakiness, required `JWT_SECRET`/`JWT_REFRESH_SECRET` env vars). They do not affect the discovery findings above, which do not depend on running `npm test`.

## D. Generalization Score

- **Held-out repositories in scope** (Node.js + Express-style `receiver.method(path, ...)` convention): **1 of 2** (`node-express-boilerplate`). `nestjs-realworld-example-app` is correctly, honestly out of scope by architecture (decorator-based routing), not a failure of the mechanism.
- **Produced fully correct impact analysis:** **1 of 2** changes on the in-scope repository (the trivial CLI-script change, correctly showing no impact). The meaningful change was **partially correct**: the two new routes were found precisely, but three of the four changed files were not connected to them, for a specific, new, general reason (see below) — not fabricated, not crashed, honestly flagged as unknown.
- **Failed safely (no crash, no fabrication):** **4 of 4** held-out runs, without exception. Every run produced `probability: UNKNOWN`, never invented a risk level, and — critically — the one real discovery miss was surfaced as an explicit "may be outside this analyzer's discovery scope" unknown rather than silently treated as no-impact.
- **Crashed:** **0**.
- **New capability regressed:** **0** — both v6 fixes (comment-awareness, controller-method-by-property-access) were re-verified end-to-end against the exact repository that found them and now work correctly there.
- **New discovery gap found:** **1** — CommonJS `module.exports = { name1, name2, ... }` object-literal export shorthand is not recognized by `find_exported_names()` (see Remaining Limitations #1).

## E. Overfitting Check

**No repository-specific rules were introduced.** Confirmed by direct inspection of the frozen diff (`git diff f45d44d..7a12b18 -- slice/discovery.py slice/analyze_change.py`): both files contain zero references to `social-media-mini`, `user-management-app`, `expressjs/express`, `edwinhern/express-typescript`, `ai-agents`, `langgraph-demo`, `node-express-boilerplate`, `nestjs-realworld-example-app`, or any specific filename, route path, or component name. Both fixes this round (comment-stripping, root-identifier resolution) are general capability extensions applicable to any JS/TS repository using the supported calling convention. The one new limitation found this round (`module.exports = {...}` object-literal shorthand) was **not** fixed — per the required process, it is documented below as a candidate for a future, separate, general fix, not patched reactively to make this round's held-out repository pass.

## F. Remaining Limitations

1. **NEW — CommonJS `module.exports = { name1, name2, ... }` object-literal export shorthand is not recognized.** `find_exported_names()` currently recognizes `export const`/`export function`/`export default function`/`export { }` (ESM forms) and `(module.)?exports.X = ...` (CommonJS property-assignment form), but not the very common plain-CommonJS pattern of defining named consts and exporting them together as an object literal at the bottom of the file (`hagopj13/node-express-boilerplate`'s `auth.controller.js` does exactly this). Effect observed: a route-registration file that itself changed was still analyzed correctly (direct impact via the route-file diff), but the controller/service/validation files it depends on — which are called as route handlers via `authController.logout` — were not connected back to those routes when only the controller file changes without the route file also changing. **This is a generic discovery bug** (missing coverage of a standard export form), not a repository-specific quirk: this export style is arguably the more traditional plain-Node.js pattern, predating widespread Babel/ESM transpilation in Express boilerplates. Not fixed in this round, per the freeze discipline; the safety design meant this did not produce a false "no impact" claim — it was correctly flagged as an unknown ("may be a file outside this analyzer's discovery scope") rather than silently treated as safe.
2. **Non-decorator, non-`receiver.method(path)` routing conventions remain entirely out of scope, by design** (re-confirmed this round on `nestjs-realworld-example-app`'s `@Get`/`@Post` decorators). The system degrades safely here: no crash, no fabricated risk level, every changed file explicitly flagged as a possible scope gap.
3. **Non-Node ecosystems remain entirely out of scope** (known, previously disclosed, by design; not re-tested this round since both fresh held-out repositories were Node.js).
4. **No real AST parsing** — a design choice, not a defect. The regex-based approach has now correctly handled component/route conventions from six distinct real repositories without repository-specific modification (`services/<name>/`, flat root components, `agents/<name>/`, a single-component repo with arbitrary receivers, a layered controllers/services/validations repo, and correctly refusing a decorator-based one) — but limitation #1 above is exactly the kind of thing a real parser would not get wrong.

## G. Recommendation

**`NEEDS_MORE_WORK`**

Not `READY_FOR_NEXT_STAGE`: this round found a new, general, previously-unseen discovery gap (`module.exports = {...}` object-literal shorthand) on the very first fresh held-out repository tested — a common, real-world CommonJS pattern, not an edge case. Shipping without addressing it would mean controller/service-layer changes in plain-CommonJS repositories can silently miss route attribution more often than the current known-repository suite would suggest.

Not `ARCHITECTURE_BOUNDARY_CONFIRMED`: this round also produced real positive evidence — both v6 fixes generalized correctly to the repository that originally found them, the new route-level detection on `node-express-boilerplate` was precise on both a meaningful and a trivial change, and the NestJS repository was refused safely and honestly rather than mishandled. The discovery approach has not hit a hard ceiling; it found one more nameable, general, addressable gap, consistent with the pattern of the last two rounds.

**North-star answer for this round:** the two v6 fixes did generalize — they were not repository-specific patches, and they worked unmodified on the exact repository that had exposed them. But the same held-out discipline immediately surfaced a new gap of the same general character (a common export-syntax form the discovery mechanism doesn't yet recognize), which is exactly the signal the business owner asked this process to produce: real generalization evidence, not diminishing returns, and not yet a stable stopping point either.

---

## Summary for the Business Owner

- **Frozen commit SHA:** `7a12b18`
- **Test results:** 57/57 automated tests pass (10 new this round: 7 comment-awareness, 3 controller-method resolution)
- **Known-repository results:** 5/5 pass, including a fresh end-to-end re-verification of both v6 fixes against the exact repository that found them
- **Held-out results:** 2 fresh repositories tested (1 in scope, 1 correctly out of scope); the in-scope repository (`node-express-boilerplate`) correctly and precisely identified two new routes and correctly discriminated a trivial change from a meaningful one, but also surfaced one new general discovery gap (CommonJS object-literal export shorthand) — recorded honestly, not hidden, and not fixed in this round
- **Recommendation:** `NEEDS_MORE_WORK`
