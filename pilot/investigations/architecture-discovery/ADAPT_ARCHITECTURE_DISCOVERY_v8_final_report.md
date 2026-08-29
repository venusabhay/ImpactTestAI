# ADAPT_ARCHITECTURE_DISCOVERY — Final Business Report (v8)

**Branch:** `feature/adapt-architecture-discovery` (not merged to `main`)
**Freeze commit:** `77d90c7`

---

## A. Implementation

**What changed.** `find_exported_names()` did not recognize the CommonJS object-literal export shorthand (`module.exports = { getUsers, createUser }`, and the explicit-key form `module.exports = { getUsers: impl }`) — only ESM `export const/function/{}` and CommonJS `exports.X = ...` property assignment. Three additions, all in `discovery.py`:

1. **`_extract_balanced()`** — a general, delimiter-agnostic balanced-bracket scanner, string/template-literal aware. Not specific to object literals.
2. **`_split_top_level()` + `_object_literal_export_names()`** — given the body of a `{ ... }` literal, splits it on top-level commas (respecting nested brackets/strings) and extracts each entry's property name: shorthand (`a`), explicit key:value (`a: impl` — the exported name is the KEY, not the local value), and quoted keys. Spread (`...x`) and computed (`[x]: ...`) entries are skipped, not guessed.
3. **`_whole_module_import_aliases()` + a new resolution mode in `_resolve_arg_to_export()`** — the object-literal case is the mirror image of the already-supported class-instance-singleton case (v7). There, a *named* import binds a local identifier to one specific export, and a class *method* on it is not itself an export (root-identifier match). Here, a whole-module `require()`/default-import binds an *arbitrary* local alias to the entire exports object, and the *property* name is the actual export (property match). Resolving this correctly requires knowing, in the *consuming* file, that the root identifier is a whole-module alias for the *changed file specifically* — not matching any `X.propertyName` in the codebase that happens to share a property name, which would be a false-positive risk.

**Why it is generic.** All three additions recognize a syntactic *shape* (a balanced object literal assigned to `module.exports`; a whole-module `require`/`import` binding), not any specific file, property, or repository name. The resolution logic is symmetric with the existing class-instance mechanism, not a parallel special case.

**What was deliberately not changed.** No AST/parser was introduced. No Python, NestJS, Java/Spring, dynamic route resolution, frontend analysis, production telemetry, or CI-history logic was touched. `design8.md`, `design9.md`, `RiskAssessment` semantics, `probability` handling, `risk_level` thresholds, and the `ESCALATE`/`REQUIRE_ADDITIONAL_VALIDATION`/`ACCEPT` rules are unchanged — confirmed by inspection of the frozen diff.

## B. Regression Results

**Total automated tests:** 66/66 pass (9 new: object-literal shorthand properties, explicit key:value, spread/computed-key exclusion, nested-brace values not leaking as top-level exports, quoted keys, comment-blindness, the exact real-world controller pattern end-to-end, and direct unit tests of the two new general helpers).

**Known-repository results:**

| Repository | Change | Result |
| --- | --- | --- |
| social-media-mini | `/verify` caching (Stage 2B) | ✅ Security regression reproduces identically — real `npm test` run, identical `SECURITY REGRESSION` assertion and failure |
| user-management-app | Change A (API caching) | ✅ `CRITICAL` risk, 4 middleware-dependent routes, unchanged |
| user-management-app | Change B (frontend validation) | ✅ `LOW` risk, empty impact, unchanged |
| user-management-app | Change C (contract break) | ✅ `MEDIUM` business impact/exposure, still visibly distinct from B |

(Change A/B/C compared via `--no-run` — these fixtures' fresh copies had no `node_modules` installed in this environment; risk/impact levels are identical to prior full-validation rounds, only the `DECISION` line differs due to `--no-run`'s "no validation ran → `ESCALATE`" default, an artifact of the comparison method, not a policy change.)

**Previously discovered regression results:**

| Repository | What was re-verified | Result |
| --- | --- | --- |
| `edwinhern/express-typescript` | v6/v7 class-instance-method resolution unaffected | ✅ `GET /` and `GET /:id` still connect via `userController.getUsers`/`getUser` |
| `hagopj13/node-express-boilerplate`, commit `750feb5` (the repository that exposed this round's gap) | The fix works on the exact repository/commit that found it | ✅ `auth.controller.js`'s `module.exports = { register, login, logout, refreshTokens, forgotPassword, resetPassword }` now correctly connects to all 6 routes that reference it via `authController.<method>`, each with precise evidence. `auth.service.js` and `auth.validation.js` remain correctly unconnected — transitive/call-expression dependencies, correctly out of this mechanism's scope, not misattributed. |

## C. Held-Out Results

Selected only after freeze commit `77d90c7`, none inspected before that point. None of `social-media-mini`, `user-management-app`, `expressjs/express`, `edwinhern/express-typescript`, `hagopj13/node-express-boilerplate`, `ai-agents`, `langgraph-demo`, or `nestjs-realworld-example-app` were reused.

| Repository | Architecture | Change tested | Expected | Actual | Result |
| --- | --- | --- | --- | --- | --- |
| `r-spacex/SpaceX-API` (10.9k★, real, actively maintained public API) | **Koa** + `koa-router`, ESM, single component — a different web framework than any tested before, using the same `receiver.method(path, ...)` convention | Real commit `66dbd9c` — "Add default sort for all launches", modifies two existing `router.get('/', ...)` handler bodies | Both routes discoverable as direct impact | ✅ Both `GET /` routes (v4 and v5) correctly identified, precise line ranges, `HIGH` confidence | ✅ **Pass — clean generalization to a new framework** |
| `r-spacex/SpaceX-API` | Same | Real commit `be59706` — docs-only typo fix (`docs/v4/landpads/update.md`), no source file touched | Empty impact | ✅ Empty impact, `LOW` risk, zero `IMPORTANT UNKNOWNS` | ✅ **Pass — correct discrimination** |
| `Tony133/fastify-api-boilerplate-jwt` (591★, real, actively maintained; **Fastify** + TypeScript + TypeBox) | Fastify, single component, route calls formatted across multiple lines (`fastify.get(\n  "/",\n  {...},\n  handler\n)`) | Real commit `88d85b3` — a 16-file refactor including a one-line comment removal in `users.routes.ts` | Low impact for this specific diff; but is the framework itself in scope? | "no route-level change detected" — **not because the change was low-impact, but because zero of this file's 9 `fastify.<method>(...)` calls are ever detected at all** (confirmed independently: `find_route_registrations` found 0/9 real call sites in this repository's `src/`) | ❌ **New general discovery gap found** — see below |
| `Tony133/fastify-api-boilerplate-jwt` | Same | Real commit `3ac585c` — dependency bump (`typebox`), no source files touched | No impact | ✅ Empty impact, `LOW` risk, zero unknowns | ✅ **Pass — correct discrimination** |
| `davellanedam/node-express-mongodb-jwt-rest-api-skeleton` (910★, real, actively maintained; Express, CommonJS, per-domain barrel/`index.js` re-export pattern) | Express, single component, mixed call formatting (some files single-line, some multi-line); every domain's individual controller files export via `module.exports = { name }` and are re-exported through a barrel `index.js` using the same shorthand | Real commit `effc2b1` — the **exact original commit that converted this repository from the already-supported `exports.updateProfile = ...` form to the object-literal `module.exports = { updateProfile }` form** the v8 fix targets | The new object-literal form should now be recognized | ✅ Confirmed directly: `find_exported_names()` on the post-commit file returns `{'updateProfile'}` — the fix works correctly in isolation. ❌ But the route (`routes/profile.js`) was **not** connected, because it imports the *barrel* `../controllers/profile` (which Node resolves to `index.js`), not `updateProfile.js` directly — a pre-existing, already-known transitive-import limitation, unrelated to this round's fix | ⚠️ **Partial — fix verified correct at the unit level; a separate, pre-existing limitation masks it end-to-end for this repository's architecture** |
| `davellanedam/node-express-mongodb-jwt-rest-api-skeleton` | Same | Real commit `a104ed3` — a real bug fix in an internal DB-helper function (removes an extra argument), no route file touched | No route impact | ✅ Empty impact, `LOW` risk, correctly flagged as an honest unknown (source files changed, not silently ignored) | ✅ **Pass — correct discrimination** |

**Quantified confirmation of the multi-line gap** (not scored per-repository above, but decisive supporting evidence): running `find_route_registrations()` against every route file in each held-out repository and comparing against a plain regex count of `receiver.method(` call sites of any formatting:

| Repository | Call sites present | Call sites detected |
| --- | --- | --- |
| `r-spacex/SpaceX-API` (single-line style throughout) | 99 | 99 (100%) |
| `Tony133/fastify-api-boilerplate-jwt` (multi-line style throughout) | 9 | 0 (0%) |
| `davellanedam/node-express-mongodb-jwt-rest-api-skeleton` (mixed style) | 21 | 7 (33%) |

## D. Overfitting Audit

- **Were repository-specific rules added?** No. `git diff 7a12b18..77d90c7 -- slice/discovery.py slice/analyze_change.py` contains zero references to any repository name, filename, route path, or property name used in this or any prior round's testing (checked by direct grep against every repository name used across all rounds).
- **Were filenames/routes/repository names special-cased?** No. The three new functions operate on syntactic shape only (`{ ... }` after `module.exports =` or `exports =`; `require(...)`/`import ... from` binding forms) — nothing about `getUsers`, `updateProfile`, `authController`, or any other specific identifier appears in the implementation.
- **Were held-out repositories selected only after freeze?** Yes. All three (`r-spacex/SpaceX-API`, `Tony133/fastify-api-boilerplate-jwt`, `davellanedam/node-express-mongodb-jwt-rest-api-skeleton`) were selected and cloned after freeze commit `77d90c7` existed, and none had been inspected, used, or referenced in any prior round.

## E. Limitations Discovered (documented, not fixed this round)

1. **NEW, most significant — route-call detection is strictly line-based.** `find_route_registrations()` requires the `receiver.method(` opening and its path-string literal to appear on the *same source line*. Any call formatted with the path argument on a following line — extremely common with Prettier/Standard multi-argument formatting, and the *default* style in the Fastify+TypeBox repository tested — is never detected, regardless of TypeScript generics or any other factor. Quantified above: 0% detection in one repository, 33% in another with mixed formatting. This is a **generic discovery capability gap** (a scanning-strategy limitation, not an architectural mismatch — the calling convention itself is exactly the declared in-scope `receiver.method(path, ...)` shape) and is the clear candidate for the next milestone: extend route-call detection to scan across a bounded multi-line window (or re-use the existing balanced-paren `call_text` reconstruction *before* attempting the path-literal match, rather than after).
2. **Confirmed, not new — transitive (barrel/`index.js`) import resolution is not followed.** The middleware/dependency mechanism connects a changed file to a route only when the *route file itself* imports the changed file by name (or via its parent directory's implicit `index.js`, which is also not recognized as a match). A common per-domain `controller/index.js` barrel pattern — re-exporting several individual controller files' exports as one object — defeats this one-hop mechanism even though the underlying export-name resolution is completely correct. This was previously an implicit limitation of the design; this round is the first to demonstrate it concretely with a real repository and a real historical commit.
3. **Non-Express/Koa/Fastify-shaped conventions remain entirely out of scope, by design** (not re-tested this round; confirmed in v7 on NestJS's decorator routing).
4. **No real AST parsing** — a design choice. The regex-based approach correctly handled a materially different framework (Koa) this round without modification, real evidence the approach generalizes across frameworks that share the calling convention — but limitation #1 is exactly the kind of thing a real parser, or even a less naive scanner, would not get wrong.

## F. Product Assessment

**`NEEDS_MORE_WORK`**

Not `READY_FOR_NEXT_STAGE`: this round's held-out testing found a severe, general discovery gap (line-based route-call scanning) with a measured 0-33% detection rate on two of the three fresh repositories tested — a materially larger failure mode than anything found in v6 or v7, on the very first attempt at a new framework and a new real-world formatting convention. Shipping without addressing it would understate the analyzer's real miss rate on genuinely common code styles.

Not `ARCHITECTURE_BOUNDARY_CONFIRMED`: the round also produced real, clean positive evidence — the object-literal export fix is directly confirmed correct at the unit level on a third, freshly-selected repository using the *exact* historical commit that introduced the pattern there, and works fully end-to-end on the repository that originally exposed the gap. Separately, the underlying discovery mechanism (component/route detection, not just this round's specific fix) generalized cleanly to an entirely new framework (Koa) it had never encountered, with 2/2 correct results including precise meaningful-vs-trivial discrimination. The approach has not hit a hard ceiling — it has, however, hit a bigger and more consequential formatting-driven gap than prior rounds' fixes addressed.

**Answer to the governing question** ("does generic export discovery improve analysis on repositories that engineering did not use while implementing the change?"): **partially, and unevenly.** The specific fix under test (object-literal export shorthand) is demonstrably correct in isolation on a fresh repository, and demonstrably correct end-to-end on the repository that exposed it — but its real-world value on fresh repositories was masked in one case by a pre-existing limitation (barrel imports) and made moot in another case by a separate, larger limitation (multi-line calls) that this round did not target. The most important, most actionable outcome of this round is not the CommonJS fix's own generalization story — it is the discovery, with hard numbers, of a bigger problem than the one this round set out to fix.

---

## Summary for the Business Owner

- **Frozen commit SHA:** `77d90c7`
- **Test results:** 66/66 automated tests pass (9 new this round)
- **Known-repository results:** 5/5 pass, including a fresh end-to-end confirmation that the fix resolves the exact real-world case that motivated this round (`hagopj13/node-express-boilerplate`)
- **Held-out results:** 3 fresh repositories tested (all in the declared Node.js/Express-style scope): one (Koa) fully generalized with no new issues; one (a repository using the exact historical commit that introduced this round's target pattern) confirmed the fix correct in isolation but exposed a separate, pre-existing transitive-import limitation; one (Fastify) surfaced a new, more severe, general discovery gap — multi-line route-call formatting — measured at 0-33% detection across the two repositories affected by it
- **Recommendation:** `NEEDS_MORE_WORK` — next candidate milestone: generalize route-call detection beyond single-line matching
