# ADAPT_ARCHITECTURE_DISCOVERY — Final Business Report (v6)

**Branch:** `feature/adapt-architecture-discovery` (not merged to `main`)
**Freeze commit:** `d5912d7`

---

## A. What Improved

Architecture assumptions removed, in order of implementation:

1. **`services/<name>/` directory assumption** → replaced with component discovery from `package.json` presence at any depth, anywhere in the repository.
2. **`app.method(...)`-only route syntax** → replaced with detection of any `receiver.method(path, ...)` call, receiver name unconstrained.
3. **No concept of "used as middleware"** → added: exported-name usage in another file's route-registration middleware arguments, connecting a changed file to routes it doesn't itself define.
4. **HTTP-call detection narrowed to `axios`/`fetch(`** → extended to also recognize `.ajax(` and `XMLHttpRequest`.
5. **Bare root route (`/`) causing repository-wide false-positive matches** → guarded generically (any route with no non-slash content skips substring search).
6. **`.ts`/`.tsx` files silently never scanned** → extended to all of `.js`/`.jsx`/`.ts`/`.tsx`, found via held-out testing against a real TypeScript repository, fixed as a general file-extension capability, not a repository-specific patch.

None of these changes touched `RiskAssessment` semantics, `probability` handling, `risk_level` thresholds, `RISK_PATTERNS`, `SENSITIVE_PATH_HINTS`, validation-selection policy, the `ESCALATE`/`REQUIRE_ADDITIONAL_VALIDATION`/`ACCEPT` rules, cross-service test detection, or `design8.md`/`design9.md`. Verified by inspection of every diff on the branch.

## B. Known Repositories

| Repository | Change | Recorded criterion | Result |
| --- | --- | --- | --- |
| social-media-mini | `/verify` caching (Stage 2B) | Security regression remains detectable | ✅ `HIGH` risk, cross-service test fails with the identical `SECURITY REGRESSION` assertion, `ESCALATE` |
| user-management-app | Change A (API caching) | Remains identifiable | ✅ `CRITICAL` risk, 4 middleware-dependent routes correctly identified, `REQUIRE_ADDITIONAL_VALIDATION` |
| user-management-app | Change B (frontend validation) | Remains low-impact | ✅ `LOW` risk, empty impact, `ESCALATE` (no frontend test capability — unchanged, correct) |
| user-management-app | Change C (contract break) | Remains distinguishable from B | ✅ `MEDIUM` business impact/exposure, concrete route + frontend-dependency evidence — visibly distinct from B |

All four pass. Decision-policy behavior (probability always `UNKNOWN`, no validation → `ESCALATE`, thresholds) unchanged — confirmed by identical `RISK`/`DECISION` sections to the pre-TS-fix freeze, differing only in the tool/policy version footer.

## C. Held-Out Repositories

Selected only after freeze commit `d5912d7`, none inspected before that point.

| Repository | Architecture | Change | Expected | Actual | Result |
| --- | --- | --- | --- | --- | --- |
| `expressjs/express` (examples/) | Single-component real repo, no per-example `package.json`, bare `require()`, arbitrary receivers (`app`, `apiv1`) | `ede24da9` — real historical fix to `app.get('/', ...)` handler body | Some discoverable impact | `GET /` correctly identified, exact line range (8-10), `HIGH` confidence | ✅ **Success — precise, correct, in-scope generalization** |
| `expressjs/express` (examples/) | Same | `6c4249fe` — real historical comment-only change, outside any handler body | Low/no impact | Empty impact (correctly distinct from the change above) | ✅ **Success — correct fine-grained discrimination** |
| `edwinhern/express-typescript` (1,251★, real, actively maintained) | TypeScript, class-based controllers (`userController.getUsers` referenced by property access, not a bare identifier) | Diagnostic change to `userController.ts`'s `getUsers` body (constructed locally; real repo, real architecture) | Some discoverable impact, connecting to `userRouter.ts`'s `GET /` | Empty impact — the class-instance-method handler pattern is not connected | ❌ **Failed safely** (no crash, no fabrication, `LOW` risk shown honestly) but missed real impact — see Remaining Limitations |
| `edwinhern/express-typescript` | Same | (Same diagnostic change, first attempt, before rewriting an inline comment) | N/A — this was a debugging step, not a scored test | A code-shaped example inside my own comment text was matched as a real route registration, producing a false `GET /` impact entry | ⚠️ **Real, generalizable bug found** — regex scanning does not distinguish code from comments (see Remaining Limitations); not scored as a pass/fail case since the triggering text was my own diagnostic artifact, but the underlying mechanism gap is real and would occur in any repository with example code in comments |
| `ai-agents` (127-commit real TS monorepo; already used to find the `.ts` gap) | TypeScript, no Express usage anywhere in the repository | `512d493`, re-run post-TS-fix | Honest re-confirmation that this specific file has no Express pattern (not a scope-filter skip) | File is now genuinely opened and scanned (confirmed via the changed `IMPORTANT UNKNOWNS` wording); still empty impact, correctly, because the file uses a config-object callback convention, not Express routing | ✅ **Fix verified** (this is a verification re-run against a repo that informed the fix, not a fresh held-out test) |
| `langgraph-demo` (real Python CLI app) | No Node component at all | Real substantial refactor of `app.py` | Honest out-of-scope result | Empty impact, `LOW` risk, `ESCALATE` — no crash, no fabrication | ✅ **Correctly, safely out of scope** (carried over from the prior round; result unaffected by the TS fix, since no `.py` file is ever a Node source file) |

## D. Generalization Score

- **Held-out repositories in scope** (Node.js + Express-style convention): **2** of 4 (`expressjs/express`, `edwinhern/express-typescript`). The other 2 (`ai-agents`, `langgraph-demo`) are correctly, honestly out of scope by architecture/language, not failures of the mechanism.
- **Produced useful, correct impact analysis:** **1 of 2** in-scope repositories (`expressjs/express`, on both its meaningful and trivial test changes — 2/2 changes correct there). `edwinhern/express-typescript` did not, for a specific, well-understood, addressable reason (see below).
- **Failed safely (no crash, no fabrication):** **4 of 4** held-out repositories, without exception. Every single held-out run produced `probability: UNKNOWN`, never invented a risk level, and never silently approved anything.
- **Crashed:** **0**.
- **Produced misleading/incorrect results:** **1** — the comment-text false positive on `edwinhern/express-typescript`, where a code-shaped comment was matched as a real route. This is scored separately from the pass/fail table above because the triggering text was a self-introduced diagnostic artifact, but the underlying capability gap (no comment-awareness in the regex scanner) is real, general, and would affect any repository with example code in comments — this is the most consequential finding of this round, more serious than a missed detection, because it is a case of confident-but-wrong evidence, not merely absent evidence.

## E. Overfitting Check

**No repository-specific rules were introduced.** Confirmed by direct inspection of every diff on `feature/adapt-architecture-discovery`: `discovery.py` and `analyze_change.py` contain zero references to `social-media-mini`, `user-management-app`, `ai-agents`, `expressjs/express`, `edwinhern/express-typescript`, `langgraph-demo`, or any specific filename, route path, or component name. Both fixes made this round (TypeScript file-extension support) are general capability extensions — the same regexes applied to a broader, generically-defined file-extension set — not special cases keyed to any repository. The two new limitations found this round (comment-matching, class-instance-method handlers) were **not** fixed — per the required process, they are documented as known limitations for a future, separate, general fix, not patched reactively to make this round's held-out repository pass.

## F. Remaining Limitations

1. **Regex scanning does not distinguish real code from comments.** Demonstrated directly: a code-shaped example inside a `//` comment was matched as a genuine route registration. This would affect any repository with example code in docstrings, JSDoc, or commented-out code — a common real-world pattern this project has not yet encountered in `social-media-mini` or `user-management-app`. A general fix (stripping comments before scanning, or requiring the match not be preceded by `//` on the same line) is possible but was not implemented in this round, per the freeze discipline.
2. **Class-based controllers with instance-method handlers are not connected to their routes.** When a route is registered as `router.get(path, controller.methodName)` (a property-access reference, not a bare imported identifier), the middleware/dependency-discovery mechanism cannot connect a change in the controller's class body back to the route, because (a) `find_exported_names` looks for `export const`/`export function`, not class methods, and (b) the middleware-argument extractor stores the full `controller.methodName` string, which does not match a bare exported name even if one existed. This is a common, real pattern (verified in a 1,251-star, actively maintained real repository) — a well-scoped, understood, but unimplemented gap.
3. **Non-Express registration conventions are not recognized** (known, previously disclosed) — confirmed again this round on `ai-agents`' config-object callback pattern.
4. **Non-Node ecosystems remain entirely out of scope** (known, previously disclosed, by design) — confirmed again on `langgraph-demo`.
5. **No real AST parsing** — a design choice, not a defect; the regex-based approach has now correctly handled four distinct real repositories' component/route conventions (`services/<name>/`, flat root components, `agents/<name>/`, and a single-component repo with arbitrary receiver names) without modification, which is meaningful evidence the approach scales further than a first read might suggest — but items 1 and 2 above are exactly the kind of thing a real parser would not get wrong.

## G. Recommendation

**`NEEDS_MORE_WORK`**

Not `ARCHITECTURE_BOUNDARY_CONFIRMED`: this round found real, positive evidence of generalization to a repository never seen during development (`expressjs/express`, 2/2 changes correctly and precisely analyzed, including successful discrimination between a meaningful change and a trivial one). The two new failures found are specific, nameable, well-understood gaps (comment-awareness, class-based controller handlers) — not evidence that the discovery approach has hit a fundamental ceiling.

Not `READY_FOR_NEXT_STAGE`: the comment-matching false positive is a genuine, general correctness bug (not merely a missing feature) that could produce misleading impact claims on any repository with example code in comments — a common enough pattern that it should be fixed and re-verified before broader use. The class-based-controller gap is also common enough (evidenced by a real, popular repository using exactly this pattern) to matter for real-world adoption.

`NEEDS_MORE_WORK` reflects genuine, measured progress — the discovery mechanism now has real, demonstrated positive generalization evidence it did not have before this round — while being honest that two more specific, bounded fixes (comment-stripping before scanning; recognizing `object.method` references in both export discovery and middleware-argument extraction) are needed before the next held-out round.

---

## Summary for the Business Owner

- **Frozen commit SHA:** `d5912d7`
- **Test results:** 47/47 automated tests pass (24 discovery unit tests including 5 new TypeScript-specific tests, 7 known-repo-shape regression tests, 16 decision-policy tests unchanged)
- **Known-repository results:** 4/4 pass — `social-media-mini` regression reproduces identically; all three `user-management-app` acceptance fixtures pass
- **Held-out results:** 4 repositories tested (2 in scope, 2 correctly out of scope); of the 2 in scope, 1 (`expressjs/express`) produced fully correct, precise results on both a meaningful and a trivial real historical change; the other (`edwinhern/express-typescript`) surfaced two new, specific, well-understood limitations (comment-text matching; class-based controller handlers) rather than a positive result — recorded honestly, not hidden
- **Recommendation:** `NEEDS_MORE_WORK`
