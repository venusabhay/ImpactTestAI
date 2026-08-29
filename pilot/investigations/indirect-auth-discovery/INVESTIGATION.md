# Indirect auth/middleware discovery: investigation

## Objective and scope

Determine whether there is a generic, repository-agnostic relationship
the analyzer can safely follow to improve security-impact discovery
when authentication/authorization behavior is separated from the
changed code (Passport strategies, Express middleware registered
elsewhere, NestJS guards/decorators, JWT logic reached through imports
or framework wiring) — **without materially increasing false
positives.** The question is not whether more files could be added to
discovery; it is whether a safe, generic mechanism exists.

**Investigation only.** No analyzer behavior was changed. Confirmed:
`git diff main..investigate/indirect-auth-discovery -- slice/` is
empty for every file. `POLICY_VERSION` and `TOOL_VERSION` untouched.

## Baseline commit

`main` @ `e57cf53`. Baseline test run: **113/113 passing**, confirmed
at both the start and end of this investigation.

## 1. Current behavior — exactly how `discovery.py` works today

Read in full (`slice/discovery.py`, 517 lines) rather than inferred.

**What constitutes an auth/security match?** There is no auth-specific
logic anywhere in `discovery.py` — it is entirely generic. The only
security-specific concept anywhere in the analyzer is
`SENSITIVE_PATH_HINTS` in `analyze_change.py` (`["verify", "login",
"register", "auth", "password", "token", "payment", "admin"]`), a
substring match against **changed file/route paths**, used only to add
one point to the risk score and one line to `WHY` — it plays no role in
*discovery* (what impact is found), only in *risk scoring* (how
seriously to treat impact already found).

**What discovery actually follows** (`find_middleware_usages()`,
`discovery.py:476-517`), precisely, in order:

1. `find_exported_names(changed_text)` — every statically-visible export
   of the **changed file** (`export const`, `export function`, `module.exports.x =`,
   `module.exports = { a, b }` shorthand). If the changed file exports
   nothing, discovery stops here for this file — return `[]` immediately.
2. Walk every other source file in the repo; keep only files whose text
   contains a `from`/`require(...)` string literal matching the changed
   file's **basename stub** (`discovery.py:506`).
3. In each matching file, run the same route-registration scanner used
   for direct routes (`find_route_registrations`) — `receiver.method(path, ...)`,
   any receiver name.
4. For each route found, look at its **middleware arguments** — but
   only the ones `_middleware_args_from_call` already kept, which are
   **exactly the arguments matching `_IDENTIFIER_ARG_RE`: a bare
   identifier or a dotted property-access chain, nothing else.** An
   inline function, arrow function, object literal, or — critically —
   **a call expression** (`foo(x)`, `passport.authenticate('x')`) is
   filtered out before this step even runs (`discovery.py:168-184`).
5. `_resolve_arg_to_export` checks whether that middleware argument
   resolves back to one of the changed file's exports: directly, via
   its root identifier (`controller.getUsers` where `controller` is
   exported), or via a whole-module import alias
   (`authController.logout` where `authController` is a local alias for
   a whole-module `require`/`import` of the changed file, and `logout`
   is one of its exported properties).

**Deliberately not followed, by construction:**
- Any relationship where the connection is a **call expression**
  rather than a bare reference (`passport.authenticate('facebook')`,
  `validate(schema)`) — filtered at step 4, unconditionally, regardless
  of what the call resolves to.
- Any relationship that isn't a **direct** file-to-route link. There is
  no transitive/multi-hop traversal: if route file R imports controller
  C, and C internally calls into service S, S is never examined at all
  — the walk in step 2 only ever looks for importers of the **originally
  changed file**, never expands outward from there.
- Any relationship through a **third-party package** as the shared
  connection point (e.g. two files that both interact with the same
  imported `passport` singleton, one via `.use()`, the other via
  `.authenticate()`) — step 2's matching is keyed to the changed file's
  **own** basename stub, so a shared external dependency never links
  them.
- Any **decorator-based** or annotation-based routing convention
  (NestJS's `@Controller()`/`@Get()`/`@UseGuards()`) — `find_route_registrations`
  only recognizes the `receiver.method(path, ...)` call shape; a
  repository using decorators exclusively has **zero** discoverable
  routes at all, not just zero auth-specific ones.
- Granularity is **whole-file**, not per-symbol: `find_exported_names`
  returns every export of the changed file regardless of which
  specific lines the diff touched. If *any* line in the file changed,
  *every* export is treated as equally "changed" for matching purposes
  (see Case 4b below for a concrete consequence).

**Where discovery stops, and how it feeds the rest of the pipeline:**
a `MIDDLEWARE_DEPENDENCY` finding becomes one `affected_entities` entry
per matched route, each with `confidence: HIGH` (`analyze_change.py`'s
`build_impact_assessment`). If no relationship is found for a changed
file at all, `analyze_change.py` appends an explicit `IMPORTANT
UNKNOWNS` line ("No route or middleware relationship was discovered
for `<path>` ... not necessarily a file with no real impact") — the
system already discloses its own blind spot rather than silently
treating an unmatched file as zero-impact. Risk scoring then proceeds
from whatever `affected_entities` and `SENSITIVE_PATH_HINTS` matches
exist; a file with zero discovered relationship contributes nothing to
`structural_exposure_score` and — unless its own *path* happens to
contain a sensitive-hint substring — nothing to `sensitive_name_hit`
either.

## 2. Methodology and sample

5 of 7 real-world runs below are cited from already-committed pilot
evidence (`pilot/investigations/architecture-discovery/`); 2
(`hackathon-starter`, both findings) were run fresh for this
investigation, live, against a shallow clone of the real upstream
repository, using the actual `analyze_change.py --no-run` (discovery
only, matching the instruction's discovery-focused scope). No
repository was chosen because it was expected to demonstrate the
hypothesis — the architecture-discovery cases were originally selected
for unrelated held-out-testing purposes in an earlier milestone; only
`hackathon-starter` was picked specifically for this investigation, and
it was picked for having a real, separate `config/passport.js` file
with real historical commits touching it — not for a commit
pre-inspected to guarantee a particular outcome (the actual commit
used, `63591fa`, was the top of `git log -- config/passport.js`, i.e.
the most recent real change to that file, chosen before its diff was
read).

## 3. Per-case ground truth

### Case 1 — Passport-style strategy config + Express controller, same commit (`saisilinus/node-express-mongoose-typescript-boilerplate`, real "add bearerAuth" commit)

Source: [`pilot/cases/2026-08-28-pilot-round/case-reports/case3-auth-middleware-change.md`](../../cases/2026-08-28-pilot-round/case-reports/case3-auth-middleware-change.md).

| Question | Answer |
|---|---|
| What changed? | `src/components/auth/auth.controller.ts`, `auth.service.ts`, `src/config/passport.ts` (48 lines), `src/routes/v1/auth.route.ts`, others |
| What security behavior depends on it? | 8 routes (`/register`, `/login`, `/logout`, `/refresh-tokens`, `/forgot-password`, `/reset-password`, `/send-verification-email`, `/verify-email`) — all authentication/account-lifecycle endpoints |
| What should discovery identify? | Both `auth.controller.ts` and `passport.ts` as impacting those 8 routes (the controller directly, the Passport/JWT strategy config transitively via whatever verifies tokens on those routes) |
| What does `discovery.py` identify? | `auth.controller.ts` → all 8 routes, `confidence: HIGH` (**hit**). `passport.ts` → **zero** routes (**miss**, disclosed as an `IMPORTANT UNKNOWNS` entry) |
| What was missed? | `src/config/passport.ts`'s relationship to the same 8 routes |
| Why was it missed? | Passport strategy files register via side effect (`passport.use(new Strategy(...))` at import time, mutating a shared third-party singleton) — not via an export consumed as a bare-identifier middleware argument. See §1, "deliberately not followed." |
| Could a generic rule find it? | No safe one identified — see §4 |
| False positives that rule would introduce? | See §4, Case 4b for a concrete, already-observed instance of this exact risk |

Practical note: in this specific commit, the overall risk level was
already `HIGH`/`CRITICAL` because `auth.controller.ts` alone correctly
triggered it — the `passport.ts` miss did not change the final decision
*in this instance*, though it would matter in a change that touched
only `passport.ts` (see Case 4a, which is exactly that shape).

### Case 2 — Express controller + transitive service/validation files (`hagopj13/node-express-boilerplate`, real commit `750feb5`, "Add logout endpoint")

Sources: [`pilot/investigations/architecture-discovery/held-out-v7/node-express-boilerplate-logout-endpoint.md`](../architecture-discovery/held-out-v7/node-express-boilerplate-logout-endpoint.md) (original miss), [`pilot/investigations/architecture-discovery/regression-verification-v8/node-express-boilerplate-logout-FIXED.md`](../architecture-discovery/regression-verification-v8/node-express-boilerplate-logout-FIXED.md) (after a later, unrelated general fix).

| Question | Answer |
|---|---|
| What changed? | `auth.controller.js`, `auth.service.js`, `auth.validation.js`, `auth.route.js` — adds `POST /logout`, `POST /refresh-tokens` |
| What security behavior depends on it? | The new logout/refresh-token endpoints depend on all three files: controller (registered as route middleware), service (session/token invalidation logic the controller calls into), validation (request-shape checks the controller calls into) |
| What should discovery identify? | All three files as impacting the 2 new routes |
| What does `discovery.py` identify? | At v7: **none of the three** (miss). At v8 (after an unrelated general fix, `module.exports = {...}` object-literal export recognition, added for a *different* held-out repository's issue): `auth.controller.js` now correctly found (hit) — but `auth.service.js` and `auth.validation.js` **still** show zero relationship |
| What was missed? | `auth.service.js`, `auth.validation.js` — still missed even after the controller-level miss was fixed |
| Why was it missed? | These files are never directly referenced as a route's middleware argument at all — the *controller* is the middleware; the controller calls the service/validation functions **internally**, a second hop the walk never takes (`find_middleware_usages` only ever looks for importers of the originally-changed file, never expands past the first file it finds) |
| Could a generic rule find it? | Only via true multi-hop import/call-graph traversal — see §4 |
| False positives? | Not directly demonstrated in this case; addressed generally in §4 |

This case is important precisely because it shows the miss is **not
about auth at all** — it is a general one-hop-only traversal limit that
happens to affect auth files here (service/validation layers behind a
controller) exactly as it would affect any other layered architecture.

### Case 3 — NestJS decorator-based routing (`lujakob/nestjs-realworld-example-app`, real commit `7c7e385`, "fix: auth middleware user object")

Source: [`pilot/investigations/architecture-discovery/ADAPT_ARCHITECTURE_DISCOVERY_v7_final_report.md`](../architecture-discovery/ADAPT_ARCHITECTURE_DISCOVERY_v7_final_report.md), row 3.

| Question | Answer |
|---|---|
| What changed? | `auth.middleware.ts`, `user.controller.ts`, `user.decorator.ts`, `user.service.ts` |
| What security behavior depends on it? | Whatever endpoints this NestJS app exposes via `@Controller()`/`@Get()`/`@UseGuards()` decorators |
| What should discovery identify? | The affected endpoints, in principle |
| What does `discovery.py` identify? | **Nothing — the entire repository has zero discoverable routes**, disclosed honestly via `IMPORTANT UNKNOWNS` for all four files, `LOW` risk (no fabricated confidence) |
| What was missed? | Everything — but because NestJS uses no `receiver.method(path, ...)` call anywhere in the codebase, not because of anything auth-specific |
| Why was it missed? | Decorator-based routing is an entirely different calling convention from what `find_route_registrations` recognizes — this is the pre-existing, already-disclosed scope boundary (Node.js + Express-style calling convention only), not a new auth-specific gap |
| Could a generic rule find it? | Not within this investigation's scope — would require parsing TypeScript decorators, a materially larger capability than a "narrowly scoped" auth fix, and orthogonal to auth specifically |
| False positives? | N/A — nothing was fabricated; the honest empty-impact result is correct given the scope boundary |

Included to demonstrate that "NestJS guards are invisible" is real but
is a **routing-convention** gap, not an **auth-discovery** gap — fixing
it would not be a narrow auth-specific slice.

### Case 4 — Passport OAuth strategy refactor, real, freshly run (`sahat/hackathon-starter`, real commit `63591fa`, "refactor: use a common handleAuthLogin function for passport.js strats")

Run live for this investigation: `python3 analyze_change.py <clone> --against 63591fa~1 --no-run`, against the actual public repository (`sahat/hackathon-starter`, cloned locally, commit `63591fa1a3eca122fe60154c9b828778a8dee189`), `TOOL_VERSION 0.10.0-pilot`, `POLICY_VERSION` unchanged.

**The real diff:** 754 lines changed in `config/passport.js`, almost
entirely inside ~15 `passport.use(...)` OAuth strategy registration
blocks (Facebook, Google, Microsoft, Twitch, QuickBooks, Trakt, Discord,
etc. — confirmed via `git show 63591fa -- config/passport.js`, grepped
for changed lines touching `isAuthenticated`/`isAuthorized`: **zero**
changed lines in `isAuthenticated`; **one** small hunk at the very end
of `isAuthorized`). `app.js` registers routes two different ways from
this same file:

```js
app.get('/auth/facebook', passport.authenticate('facebook'));          // call expression
app.get('/account', passport.isAuthenticated, accountController.getAccount); // bare identifier
```

#### Case 4a — the OAuth routes the commit actually rewrote

| Question | Answer |
|---|---|
| What changed? | The Facebook/Google/Microsoft/Twitch/QuickBooks/Trakt/Discord/X/GitHub/LinkedIn strategy registrations |
| What security behavior depends on it? | ~10 OAuth login/callback routes: `/auth/facebook`, `/auth/facebook/callback`, `/auth/google`, `/auth/github`, `/auth/microsoft`, `/auth/twitch`, `/auth/discord`, `/auth/linkedin`, `/auth/x`, and their callbacks |
| What should discovery identify? | Those ~10 routes as impacted — this commit is precisely about how they authenticate |
| What does `discovery.py` identify? | **None of them.** The live `POTENTIAL IMPACT` list for this run contains 15 routes, and not one is an `/auth/*` OAuth route |
| What was missed? | Every OAuth login/callback route |
| Why was it missed? | `passport.authenticate('facebook')` is a call expression — filtered out at `_middleware_args_from_call` before resolution is even attempted (see §1) |
| Could a generic rule find it? | No safe one identified — see §4 |
| False positives that rule would introduce? | See §4 |

#### Case 4b — the guard-protected routes that were flagged, over-broadly

| Question | Answer |
|---|---|
| What changed? | (Per the diff: essentially nothing inside `isAuthenticated`/`isAuthorized` themselves) |
| What security behavior depends on it? | `isAuthenticated`/`isAuthorized`, unchanged by this diff, still gate `/account`, `/account/profile`, `/account/password`, `/account/delete`, `/api/steam`, `/api/tumblr`, `/api/facebook`, `/api/google/drive`, and 7 more |
| What should discovery identify? | Nothing new about these 15 routes — the functions that guard them did not change |
| What does `discovery.py` identify? | **All 15 routes**, `confidence: HIGH`, "exports `isAuthenticated`, `isAuthorized`, used as middleware by..." |
| What was (over-)claimed? | That this commit's change is relevant to `isAuthenticated`/`isAuthorized`-guarded routes |
| Why? | Whole-file granularity: `find_exported_names()` reports *every* export of `config/passport.js`, with no per-symbol diff-line attribution — a 754-line rewrite of ten unrelated OAuth strategies makes the file "changed," so *every* export of that file is treated as equally implicated, including two functions with zero (`isAuthenticated`) or one line (`isAuthorized`) actually touched |
| **This is a demonstrated, real false positive** | Not hypothetical — it is the literal output of the live run cited above |

This is the single most important pair of findings in this
investigation: the same real commit, the same file, produces **both** a
concrete miss (Case 4a, under-detection) **and** a concrete false
positive (Case 4b, over-detection) from the *same* underlying
mechanism, in opposite directions.

## 4. Candidate generic mechanisms — explicitly tested and rejected

| Mechanism | Would it catch the misses (1, 2, 4a)? | False-positive cost | Verdict |
|---|---|---|---|
| **Broaden import-graph traversal**: any file importing the changed file (not just ones using it as a bare-identifier middleware arg) is "impacted" | Yes, for Case 1/4a (`app.js` does `require('./config/passport')`) | **Unbounded.** Nearly every file in a typical app imports shared config/logging/db modules; this would mark huge, unrelated swaths of the codebase as security-relevant on every change to any shared module | **Rejected** |
| **Follow call-expression middleware args** (e.g. resolve `passport.authenticate(...)` back to the strategy file) | Yes, for Case 4a specifically | Requires recognizing that a *local* alias (`passport`) refers to a *third-party* singleton object also mutated, elsewhere, by a *separately-imported*, side-effect-only local file — a transitive, singleton-mediated relationship. A safe, general version of this (not specific to the `passport` package/API) was not found; any version narrow enough to be safe would need to hardcode the Passport API shape (`.use()`/`.authenticate()`), which is exactly the kind of framework-specific special-casing excluded by instruction | **Rejected** |
| **App-level (`app.use(x)`) registration as "affects everything"** | Yes, trivially, for any Passport-initialized app | Collapses to "any change to this file impacts the entire application" — provides no discriminating signal at all, and is functionally equivalent to hardcoding "this file is always critical," not a structural discovery improvement | **Rejected** |
| **True multi-hop import/call-graph traversal** (fixes Case 2's service/validation miss) | Yes, for Case 2 | Not shown to be unsafe, but is a **materially larger capability** than "a narrowly scoped auth fix" — real call-graph construction across an arbitrary JS/TS codebase, general to all layered architectures, not just auth. Out of proportion to this investigation's scope | **Rejected as a "small implementation slice"; not auth-specific anyway** |
| **Symbol/line-level export attribution** (fixes Case 4b's false positive, not the misses) | No — addresses over-detection, not under-detection | Would reduce false positives if built, but does not answer this investigation's question (does a *safe generic relationship* exist to *find more*) | **Out of scope for this decision; noted as a separate, real, orthogonal finding** |
| **Expand `SENSITIVE_PATH_HINTS` to include `passport`, `oauth`, `strategy`, `guard`** | Partially — would at least flag `passport.ts`/`passport.js` by filename for risk-scoring purposes (not discovery) | Same "growing ad hoc catalogue" problem already identified and rejected in the environment-failure-classification investigation for env-var names; a filename-substring list is inherently a losing race against real-world naming variety (`passport.js`, `oauth.js`, `strategies/`, `guards/`, `authz.ts`, ...) | **Rejected**, same reasoning as the prior investigation |

No mechanism considered is both (a) genuinely generic/repository-agnostic and (b) demonstrated safe against the false-positive risk already observed live in Case 4b.

## 5. False-positive analysis

Case 4b is a real, already-occurring false positive under **today's**
mechanism, not a hypothetical consequence of a proposed change: a
754-line OAuth refactor that touches zero lines of `isAuthenticated`
still causes 15 unrelated, unchanged routes to be reported as
"depends on... as middleware" with `confidence: HIGH`. Any mechanism
proposed to fix Cases 1/2/4a's misses that works by *further widening*
what counts as a relationship (broader import-following, call-expression
following, app-level registration) would apply on top of this same
whole-file granularity — making the existing, already-real over-broad
claim spread across a *larger* set of files and routes, not a smaller
one. A narrowing fix (symbol/line-level attribution) exists in
principle but does not address recall at all, and is a separate
capability from what this investigation was asked to evaluate.

## 6. Recurrence measurement

Of 4 distinct real repositories / commits examined (6 distinct
documented findings):

- **2 confirmed misses directly tied to a Passport-style or
  call-expression-based indirect auth pattern** (Case 1's `passport.ts`,
  Case 4a's OAuth routes).
- **1 confirmed miss tied to transitive (multi-hop) dependency
  traversal**, which happens to involve auth files but is not
  auth-specific (Case 2's `auth.service.js`/`auth.validation.js`).
- **1 confirmed non-finding that is a routing-convention gap, not an
  auth gap** (Case 3, NestJS).
- **1 confirmed hit** (Case 1's `auth.controller.ts`, Case 4b's
  guard-protected routes as a *relationship*, though see below).
- **1 confirmed, real false positive** from the very mechanism that
  produces the hit above (Case 4b).

**This is a sample of 4 repositories, not a statistically significant
study** — no claim is made about the true population rate of any
pattern across real-world repositories generally.

## 7. Product impact

The current behavior is already the honest one for the misses found:
every miss in this investigation was disclosed via an explicit
`IMPORTANT UNKNOWNS` entry ("this may be a file outside this analyzer's
discovery scope... not necessarily a file with no real impact") — the
tool is not claiming these files have no impact, only that it found no
evidence of impact. No fabrication occurs today. The risk this
investigation was asked to weigh is a specific one: would extending
discovery to close these gaps **generically and safely** be possible —
and the answer, demonstrated with real evidence rather than assumed, is
no, not without either framework-specific special-casing (excluded by
instruction), unbounded precision loss (Case 4b already shows this
mechanism's coarseness in production), or a capability (full call-graph
traversal) too large to call a narrow slice.

## 8. Interaction with existing behavior (regression checks only)

This investigation ran the analyzer with `--no-run` in every fresh
case, so no validation-execution paths were exercised; no interaction
with `INCONCLUSIVE`/timeout/CI-retrieval fail-safe behavior applies
here. `POLICY_VERSION`, risk scoring, confidence scoring, and
`final_recommendation()` were not touched, read, or exercised
differently than their existing, unchanged behavior. 113/113 tests pass,
confirmed at both the start and end of this investigation.

## Limitations

- 4 repositories is a small sample; a broader survey could find
  different proportions, or additional failure/success shapes not
  observed here (e.g. a framework using named — not default/namespace —
  imports of a strategy file with a truly generic, safely-followable
  connection this investigation didn't happen to encounter).
- Case 1 and Case 2's evidence is reused from an earlier, independent
  milestone (architecture-discovery v7/v8), not re-verified live in
  this investigation; only Case 4 was run fresh, live, against the
  current `main`@`e57cf53` codebase.
- This investigation did not attempt to build or prototype any of the
  rejected mechanisms in code — each was evaluated analytically against
  the real cases above, per the instruction to keep this
  investigation-only. A prototype could in principle surface additional
  false-positive shapes not anticipated here.

## Recommendation

**DEFER**

A recurring real-world blind spot exists (Cases 1, 2, 4a — 3 of 4
repositories examined). But no generic, repository-agnostic mechanism
was found that closes it without either (a) requiring framework-
specific special-casing of Passport's `.use()`/`.authenticate()` API
shape, explicitly excluded by instruction; (b) unbounded precision
loss, demonstrated concretely and non-hypothetically by Case 4b — the
same file, same commit, already produces a real false positive under
today's narrower mechanism, which any broadening would spread further;
or (c) a capability (general multi-hop call-graph traversal, full
TypeScript decorator parsing for NestJS) large enough that it would not
be a "narrowly scoped" implementation slice, and which is not
auth-specific in the first place. Per the stated decision principle:
the objective was to determine whether indirect auth impact can be
found generically enough and safely enough to justify a product
change — for the patterns examined here, it cannot yet. Preserve this
finding; the two most promising, still-unproven candidates for a future
look (should real pilot evidence make either urgent) are (1) line/symbol-
level export attribution, which would reduce today's real false-positive
rate without needing to solve recall at all, and (2) scoped multi-hop
traversal limited to a small, fixed hop count, evaluated on its own
false-positive merits — neither is proposed for implementation now.

---

## Completion gate

- [x] No `.py` source changes — confirmed empty diff.
- [x] No test changes.
- [x] No `.github/workflows/` changes.
- [x] `POLICY_VERSION` unchanged.
- [x] `TOOL_VERSION` unchanged.
- [x] No risk/probability/confidence changes.
- [x] No recommendation/`ACCEPT` changes.
- [x] No repository-specific heuristics introduced — every candidate
  mechanism that would have required one was explicitly rejected (§4).
- [x] Full existing test suite passes — 113/113, start and end.
- [x] At least 5 real cases examined — 4 real repositories, 6 distinct
  documented findings, exceeding the minimum.
- [x] Ground truth documented for every case — §3.
- [x] False positives explicitly evaluated — §4, §5, with a concrete,
  live-demonstrated instance (Case 4b), not a hypothetical.
- [x] Investigation stored under `pilot/investigations/`.
- [x] No product PR opened.
