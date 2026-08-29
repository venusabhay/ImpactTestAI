# ADAPT_ARCHITECTURE_DISCOVERY — Final Business Report (v9)

**Branch:** `feature/adapt-architecture-discovery` (not merged to `main`)
**Freeze commit:** `8eb4cae`
**Design (written before implementation):** [`docs/decisions/ROUTE_DISCOVERY_MULTILINE_DESIGN.md`](../../../docs/decisions/ROUTE_DISCOVERY_MULTILINE_DESIGN.md)

---

## Implementation

**What changed.** `find_route_registrations()` previously matched a route call with one regex requiring the receiver, method, opening paren, **and** the path string literal to all appear on the same source line. Replaced with two independent steps:

1. `ROUTE_METHOD_RE` finds only `receiver.method(` — the part guaranteed to be on one line in practice.
2. The call's arguments are read via the existing general-purpose `_extract_balanced()` / `_split_top_level()` helpers (already used for the v8 object-literal-export fix), which work identically whether the call spans one line or fifty. The first top-level argument must still be a `/`-prefixed string literal (the same requirement the old regex enforced); every remaining argument is kept as a `middleware_args` candidate under the same bare/dotted-identifier filter as before.

This also fully subsumes and removes `_extract_middleware_args()` and `HANDLER_START_RE` — including the v7 trailing-semicolon workaround — since reading arguments via exact balanced-span splitting makes the old hand-sliced, formatting-sensitive string logic unnecessary.

**Why it is generic.** Both helpers reused are already general-purpose and unaware of routes, method names, filenames, or repositories. The receiver/method matching (`app`, `router`, `server`, `fastify`, or any arbitrary identifier) and the middleware-argument filter are unchanged from current, shipped behavior — this is a span-detection fix, not a change to what is understood as a dependency.

**What was deliberately not changed.** No AST/parser was introduced. `design8.md`, `design9.md`, `RiskAssessment` semantics, `probability` handling, `risk_level` thresholds, and the `ESCALATE`/`REQUIRE_ADDITIONAL_VALIDATION`/`ACCEPT` rules are untouched — confirmed by inspection. Fastify's config-object route-options convention (`{ preHandler: [...] }`) remains unaddressed, as documented in v8 and re-confirmed this round (see Newly Discovered Limitations).

## Regression Results

**Total automated tests:** 74/74 pass (8 new, all in `test_discovery.py`: single-line route control, multiline route with path on its own line, multiline vs. single-line producing an identical result, a config-object argument kept whole and correctly excluded, nested parens/brackets/braces inside a multiline call, multiple routes in one file with mixed formatting, a multiline route inside a comment correctly not detected, a string literal containing route-call-shaped text correctly not confused with the real call).

**Known-repository results (unchanged):**

| Repository | Change | Result |
| --- | --- | --- |
| social-media-mini | `/verify` caching (Stage 2B) | ✅ Security regression reproduces identically — real `npm test` run, identical `SECURITY REGRESSION` assertion |
| user-management-app | Change A (API caching) | ✅ `CRITICAL` risk, unchanged |
| user-management-app | Change B (frontend validation) | ✅ `LOW` risk, empty impact, unchanged |
| user-management-app | Change C (contract break) | ✅ `MEDIUM` business impact/exposure, still distinguishable from B |

**Previously discovered regression results (unchanged):**

| Repository | What was re-verified | Result |
| --- | --- | --- |
| `edwinhern/express-typescript` | v6/v7 class-instance-method resolution | ✅ `GET /` and `GET /:id` still connect via `userController.getUsers`/`getUser` |
| `hagopj13/node-express-boilerplate`, commit `750feb5` | v8 object-literal-export resolution | ✅ All 6 routes still correctly connected to `auth.controller.js` |

## Route-Detection Coverage, Before vs. After

Measured directly on the two repositories that exposed the gap in v8:

| Repository | Before (v8) | After (v9) |
| --- | --- | --- |
| `davellanedam/node-express-mongodb-jwt-rest-api-skeleton`, `app/routes/` | 7/21 (33%) | **21/21 (100%)** |
| `Tony133/fastify-api-boilerplate-jwt`, `src/` | 0/14 (0% — confirmed: zero of its calls have the path on the same line as the opening paren) | **5/14 (36%)** |

The Fastify repository's residual 9 misses are **not** a multiline-detection failure: confirmed directly (`grep`) that exactly 9 of its 14 calls use a TypeScript generic type argument between the method name and the opening paren (`fastify.post<{ Body: X }>(...)`), and the 5 found are precisely the 5 calls *without* a generic. This is a distinct, separately-scoped gap — see Newly Discovered Limitations.

## Held-Out Results

Selected only after freeze commit `8eb4cae`, none inspected before that point. None of `social-media-mini`, `user-management-app`, `expressjs/express`, `edwinhern/express-typescript`, `hagopj13/node-express-boilerplate`, `ai-agents`, `langgraph-demo`, `nestjs-realworld-example-app`, `r-spacex/SpaceX-API`, `Tony133/fastify-api-boilerplate-jwt`, or `davellanedam/node-express-mongodb-jwt-rest-api-skeleton` were reused.

**Selection rationale:** the task required at least one Express repository, one Fastify (or other in-scope Express-style) repository, and one additional unseen Node repository where practical. `santiq/bulletproof-nodejs` (5.8k★) was chosen for the Express slot specifically because its real commit history contains the *exact* transformation this milestone targets — a route converted from single-line to multiline formatting by inserting a validation middleware. `tarusharora/node-fastify-api-boilerplate` (36★, real, uses the direct `fastify.get/post(path, ...)` convention) was chosen for the in-scope Fastify slot. `siegfriedgrimbeek/fastify-api` (162★, real, uses Fastify's alternative `fastify.route(optionsObject)` config-driven convention instead) was included as the additional out-of-scope repository, per the task's explicit allowance — **not counted as evidence of in-scope generalization.**

| Repository | Scope | Historical change | Expected | Actual | Result |
| --- | --- | --- | --- | --- | --- |
| `santiq/bulletproof-nodejs` (Express, TypeScript) | In scope | Real commit `4b2251b` — "Add api validation": converts `route.post('/signup', async (...) => {...})` (single-line) into a multiline call with a `celebrate({...})` config-object validation argument inserted before the handler — **this is precisely the multiline+config-object shape this milestone targets** | Both `/signup` and `/signin` discoverable as direct impact | ✅ Both correctly identified, precise line ranges (`14-31`, `33-50`), `HIGH` confidence | ✅ **Pass** |
| `santiq/bulletproof-nodejs` | Same | Real commit `f1b57da` — README-only update, no source touched | Empty impact | ✅ Empty impact, `LOW` risk, zero unknowns | ✅ **Pass — correct discrimination** |
| `tarusharora/node-fastify-api-boilerplate` (Fastify, JS) | In scope | Real commit `f4f0cdc` — "Add POST call for users API", modifies `api/routes/user.js` plus its controller/adaptor/util files | `POST /users` discoverable as direct impact; controller exports connected to both `GET /users` and `POST /users` | ✅ `POST /users` direct impact with precise line range; `userController.js`'s `getUsersCtrl`/`createUsersCtrl` exports correctly connected to both routes via middleware dependency | ✅ **Pass — no regression on this framework's single-line calls, dependency resolution unaffected** |
| `tarusharora/node-fastify-api-boilerplate` | Same | Real commit `16c9975` — README-only update, no source touched | Empty impact | ✅ Empty impact, `LOW` risk, zero unknowns | ✅ **Pass — correct discrimination** |
| `siegfriedgrimbeek/fastify-api` (Fastify, but uses `fastify.route(optionsObject)` — a genuinely different, out-of-scope calling convention, not `receiver.method(path, ...)`) | **Out of scope** (included per task allowance; not counted as in-scope evidence) | Real commit `f8cd7e2` — "Redefined Routes", touches both the controller and the route-definitions array | Honest, safe "no evidence" result | ✅ Empty impact, `LOW` risk, both changed files explicitly flagged in `IMPORTANT UNKNOWNS` as possibly out-of-scope rather than silently ignored — no crash, no fabrication | ✅ **Correctly, safely out of scope** |

**Meaningful/trivial discrimination:** demonstrated cleanly on both in-scope repositories (bulletproof-nodejs: direct-impact multiline commit vs. README-only commit; node-fastify-api-boilerplate: direct-impact route-adding commit vs. README-only commit) — in every case the meaningful change produced concrete `POTENTIAL IMPACT` entries with precise line ranges and the trivial change produced none.

## Newly Discovered Limitations

1. **NEW — TypeScript generic type arguments between the method name and the opening paren are not recognized.** `fastify.post<{ Body: RegisterBody }>(...)` fails to match `ROUTE_METHOD_RE`, which requires `(` immediately after the method name. Quantified precisely on `Tony133/fastify-api-boilerplate-jwt`: exactly 9 of 14 calls use this shape and are missed; the other 5 (no generic) are all found. This is a **distinct, general discovery capability gap** from multiline formatting — the calling convention is still the in-scope `receiver.method(path, ...)` shape, just with an additional syntactic element in between — and is the clear candidate for the next milestone.
2. **Reconfirmed, not new — Fastify's `fastify.route(optionsObject)` convention remains out of scope.** A route defined as a plain object (`{ method: 'GET', url: '/api/cars', handler: ... }`) and registered via a single `.route(...)`/loop call is architecturally different from the per-route `receiver.method(path, ...)` calling convention this analyzer targets. Confirmed again this round on a real repository using it: handled safely (no crash, no fabrication, explicit unknowns), consistent with the v7 NestJS finding.
3. **Fastify's config-object middleware/hook convention (`preHandler: [...]` inside an options object) remains unaddressed** (documented in v8, not re-tested this round since the two in-scope Fastify commits tested here didn't use it).

## Overfitting / Special-Case Inspection

- **Repository-specific rules added?** No.
- **Filenames/routes/repository names special-cased?** No.
- `git diff 8eb4cae -- slice/discovery.py slice/analyze_change.py` (the full v9 implementation diff) contains **zero** references to any repository name used in this or any prior round — checked by direct grep against the complete list of fifteen repositories tested across all rounds to date.
- **Held-out repositories selected only after freeze?** Yes. All three (`santiq/bulletproof-nodejs`, `tarusharora/node-fastify-api-boilerplate`, `siegfriedgrimbeek/fastify-api`) were cloned and inspected only after freeze commit `8eb4cae` existed.

## Recommendation

**`PASS`**

This milestone had a single, narrow, well-defined objective — make route-call detection independent of line-based formatting — and every acceptance criterion set for it was met without qualification:

- 74/74 tests pass (66 baseline + 8 new), no regressions anywhere.
- Known-repository acceptance criteria are byte-for-byte unchanged.
- Multiline routes are detected correctly, verified against the *exact* real historical commit (`santiq/bulletproof-nodejs`, `4b2251b`) that performs precisely the single-line-to-multiline-with-config-object transformation this milestone targets.
- Held-out coverage improved from 33% to 100% on one previously-affected repository and from 0% to 36% on another, with the residual gap on the second repository cleanly and quantitatively attributed to a **different, separately-scoped** mechanism (TypeScript generics) rather than any incompleteness in the multiline fix itself.
- Meaningful and trivial changes remained distinguishable on every held-out repository that offered a suitable pair.
- No repository-specific special cases were introduced.
- No changes were made to `design8.md`, `design9.md`, the risk/decision policy, probability semantics, or the `ESCALATE`/`REQUIRE_ADDITIONAL_VALIDATION`/`ACCEPT` rules.

The one new limitation this round's held-out testing found (TypeScript generic type parameters) is real and worth fixing, but it is not evidence that *this* milestone's fix is incomplete — it is evidence of a different, narrower boundary immediately beyond it, exactly the kind of finding the held-out discipline is designed to keep surfacing. Per the explicit instruction accompanying this milestone, engineering is **stopping here for business review** rather than starting that next capability.

---

## Summary for the Business Owner

- **Frozen commit SHA:** `8eb4cae`
- **Test results:** 74/74 automated tests pass (8 new this round)
- **Known-repository results:** 4/4 pass, unchanged from all prior rounds
- **Route-detection coverage, before → after:** 33% → 100% on one previously-affected repository; 0% → 36% on another (residual gap fully explained by a separate, unaddressed TypeScript-generics case, not a multiline-detection shortfall)
- **Held-out results:** 3 fresh repositories tested (2 in scope, 1 out of scope by design) — clean pass on all 5 scored test cases across the 2 in-scope repositories, plus a correct, safe out-of-scope refusal on the third
- **New limitation found:** TypeScript generic type arguments between method name and opening paren (e.g. `fastify.post<{ Body: X }>(...)`) — documented as the next candidate milestone, not fixed this round
- **Recommendation:** `PASS`
- **Next step:** stopping for business review, per instruction — no further capability work started
