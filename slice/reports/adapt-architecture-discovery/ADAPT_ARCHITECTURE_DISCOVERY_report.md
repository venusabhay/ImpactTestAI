# ADAPT_ARCHITECTURE_DISCOVERY — Final Report

**Branch:** `feature/adapt-architecture-discovery` **Freeze commit:** `d958a15` (implementation frozen before any held-out repository was selected or inspected)

---

## Executive Summary

Architecture discovery was rebuilt on evidence rather than hardcoded assumptions: components are now discovered from `package.json` presence anywhere in a repository (not only `services/<name>/`), routes from any `receiver.method(path, ...)` call (not only `app.method(...)`), and a new capability — middleware/dependency discovery — finds files used as middleware by routes defined elsewhere, via exported-name usage rather than filename matching. Re-run unchanged against both known repositories, this closed every gap the Stage 2C pilot found: `social-media-mini`'s security regression still reproduces identically, and all three `user-management-app` acceptance fixtures now pass, including the one that mattered most — the dangerous cross-component contract break (Change C) is now clearly, evidentially distinguishable from the trivial frontend tweak (Change B), where before they were byte-for-byte identical.

Held-out testing against two repositories never touched during development (`ai-agents`, a real, actively-developed TypeScript agent monorepo with 127 commits; `langgraph-demo`, a real Python CLI app) found the boundary is **narrower than originally stated**: TypeScript (`.ts`/`.tsx`) files are not scanned at all — an implementation gap, not a deliberate scope decision, discovered only by testing against a repository written in a language the two development repositories didn't use. Within that narrowed boundary, both held-out repositories produced honest, non-fabricated "insufficient evidence" results — no crash, no fake confidence, no special-casing — but also produced **zero differentiating signal** between a real bug fix and a trivial docs commit, because both changes fell outside what the frozen implementation can see at all.

**Recommendation: `NEEDS_MORE_WORK`.** The discovery mechanism is proven, tested, and demonstrably self-consistent within its actual scope; that scope needs to include TypeScript before a genuine held-out test of *within-scope* generalization becomes possible. See Recommendation for the specific reasoning.

---

## What Changed

| Before (Stage 2C) | After (this milestone) |
| --- | --- |
| Component = regex match on `services/([^/]+)/` | Component = nearest ancestor directory containing `package.json`, anywhere in the tree |
| Route = `app.(get\|post\|put\|delete\|patch)(...)` only | Route = any `receiver.(get\|post\|put\|delete\|patch\|all)(...)`, receiver name unconstrained |
| No concept of "used as middleware" | New: exported-name usage in another file's route-registration middleware arguments |
| `structural_exposure_score` = count of cross-component callers only | Broadened to also count routes reached via a discovered middleware dependency (same formula/thresholds, broader input) |
| — | Fixed in passing: import-detection regex missing `.js` extension tolerance; literal-path search flooding evidence for the bare-root route `/` |

No changes to `design8.md`, `design9.md`, `RISK_PATTERNS`, `SENSITIVE_PATH_HINTS`, or `final_recommendation()`'s decision rules. `POLICY_VERSION` → `repo-plus-ci-plus-cross-service-plus-discovery-v5`; `TOOL_VERSION` → `0.3.0-pilot`.

## What Was Tested

**Regression (known repositories, mandatory before freeze):**
- `social-media-mini`: the original `/verify` caching change, re-run unchanged.
- `user-management-app`: all three preserved acceptance fixtures (Change A/B/C), re-run unchanged from their `.patch` files.

**Held-out (selected only after the freeze commit, never inspected before):**
- `ai-agents` — a real, actively-developed TypeScript monorepo (127 commits, `agents/<name>/package.json` per sub-agent, no `services/` prefix, no Express usage anywhere in the repository). Two real historical commits analyzed: `512d493` (a genuine production bug fix — a Teams bot silently dropped messages from Azure's Web Chat test tool) and `d1a2389` (a documentation-only commit), to directly test meaningful-vs-trivial discrimination.
- `langgraph-demo` — a real Python CLI application (LangGraph-based), no `package.json` anywhere. Commit `a97edb1`, a substantial real refactor of `app.py` (67 deletions, 15 insertions).

## Analyzer Results

| Repository | Change | Expected | Actual | Correct? | Notes |
| --- | --- | --- | --- | --- | --- |
| social-media-mini | `/verify` caching | Reproduce Stage 2B security regression | `HIGH` risk, cross-service test fails with identical `SECURITY REGRESSION` assertion, `ESCALATE` | ✅ Yes | Bonus: `post-service`/`user-service` now also validated as discovered callers (not required, a legitimate side effect of broadened validation-target selection) |
| user-management-app | Change A (API caching) | Detect caching/risk concern | `CRITICAL` risk; 4 impacted routes correctly identified via middleware-dependency discovery (previously: empty) | ✅ Yes | See note on pre-existing env gap below |
| user-management-app | Change B (frontend validation) | Low/appropriate impact | `LOW` risk, empty impact, `ESCALATE` (no frontend test capability exists) | ✅ Yes | Unchanged from original pilot — correct then and now |
| user-management-app | Change C (cross-component contract break) | Materially distinguishable from B | `MEDIUM` business impact/exposure; changed route AND frontend's real dependency both identified with concrete evidence (previously: byte-for-byte identical to B) | ✅ Yes | The single most important pass/fail signal from the acceptance criteria — now passes |
| ai-agents | `512d493` (real bug fix, Teams dispatch logic) | Some discoverable impact | Empty impact, `LOW` risk, `ESCALATE` (no validation available) | ❌ No (but honestly, not fabricated) | Root cause: file is `.ts`, never opened for impact analysis — see Architecture Limitation |
| ai-agents | `d1a2389` (docs-only commit) | Low/no impact | Empty impact, `LOW` risk, `ESCALATE` — **byte-for-byte identical shape to the real bug fix above** | ⚠️ Correct outcome, wrong reason | Cannot be told apart from the real bug fix in this repository, for a different underlying cause than the original Stage 2C finding |
| langgraph-demo | `a97edb1` (real refactor of `app.py`) | Honest "out of scope" (no Node components exist) | Empty impact, `LOW` risk, `ESCALATE` | ✅ Yes | Correctly, honestly out of scope — no `package.json` anywhere in the repository; Python file never scanned |

## Ground Truth Verification (known repositories)

- **social-media-mini**: verified by temporarily reverting the caching diff and re-running — the security test passes against the original code and fails reliably against the change, 3/3 runs (re-confirmed identically to Stage 2B; this milestone did not need to re-derive it, only reproduce it).
- **user-management-app Change A**: manually confirmed `authMiddleware.js`'s `protect` export is genuinely used by 4 routes (`/profile`, `GET /`, `PATCH /:id/role`, `DELETE /:id`) via direct code inspection of `userRoutes.js` — matches the 4 routes discovery found exactly.
- **user-management-app Change C**: manually confirmed `user-management-frontend/src/utils/api.js` genuinely calls `/api/users/refresh` via `fetch` with `credentials: "include"`, no `Authorization` header on that specific call — matches the transitive dependency discovery found exactly.
- **ai-agents `512d493`**: manually confirmed via `git show` and direct file inspection that `agent/channels/teams.ts` contains no `receiver.method(path)`-shaped call anywhere — the file uses a configuration-object callback pattern (`teamsChannel({ onMessage(...) {...} })`), which is a real, different, and legitimate way to register message handling that this analyzer's Express-specific pattern was never designed to recognize even if the file were scanned.

## Validation Capability

- **social-media-mini / user-management-app**: unchanged from Stage 2B/2C — real `npm test` execution, cross-service test execution, and CI-history fetch all continue to work exactly as before.
- **ai-agents / langgraph-demo**: no validation was recommended or executed in any held-out case, because no impact was discovered to validate against, and (for `linkedin-cover-generator` specifically) no `test` script exists in its `package.json` regardless. This is a downstream consequence of the impact-discovery gap, not a separate validation-layer failure — verified by checking that `ai-agents`'s root `package.json` and `linkedin-cover-generator`'s `package.json` were correctly discovered as components; validation was never attempted because impact was never found.

## Architecture Limitation (found by held-out testing, not present in the original design doc)

**TypeScript (`.ts`/`.tsx`) files are never opened for impact analysis.** `build_impact_assessment()` and `discovery.find_middleware_usages()` both filter to `.js`/`.jsx` only. This was not a deliberate scope decision recorded in `ARCHITECTURE_DISCOVERY_DESIGN.md` — it was inherited, unexamined, from the original prototype (which only ever saw plain JavaScript repositories) and neither development repository (`social-media-mini`, `user-management-app`) is written in TypeScript, so nothing during implementation or regression testing could have surfaced it. It took a held-out repository in a different language variant to find it. The underlying regex patterns in `discovery.py` (route calls, exports, imports) are largely TypeScript-syntax-compatible already — extending the file-extension filter is expected to be a small, mechanical change, not a redesign.

**Separately, and independently confirmed:** `ai-agents` uses no Express-style HTTP framework anywhere in its ~127-commit history (verified by repository-wide search) — its message-handling patterns (Teams channel callbacks) are a legitimately different registration convention this analyzer was never designed to recognize, TypeScript or not. `langgraph-demo` has no Node component at all. Both are correctly, honestly out of scope per the original design document, and both failed safely: no crash, no fabricated impact, no invented probability, no silent "proceed."

## False Positives

None observed in either the known-repository regression or the held-out runs.

## False Negatives

- **ai-agents `512d493`**: a real, shippable bug fix (a Teams bot silently dropping user messages) produced zero impact evidence, purely because of the `.ts` file-extension gap above.
- **langgraph-demo `a97edb1`**: a substantial real refactor produced zero impact evidence — correctly, since no in-scope component exists, but still a "miss" in the sense that a human reviewing this report would learn nothing about what actually changed.

## Dangerous Confidence

None found in the held-out runs — critically, unlike the original Stage 2C finding (where two changes of wildly different risk produced identical, *confidently LOW*, reports), the held-out failures here are uniformly low-confidence and explicitly say `ESCALATE` due to *no validation being available*, not due to a confident-but-wrong risk assessment. The `ai-agents` meaningful-vs-trivial pair being indistinguishable is a real limitation (see False Negatives), but it is not a case of the tool asserting something specific and false the way the Stage 2C "test file does not import the changed module" claim was — it simply found nothing to say, in both cases, honestly.

## Reusable Capabilities (worked without modification, across all repositories tested)

- Git diff/ref mechanics, regardless of repository or commit structure (tested against a single-commit repo, a 127-commit repo, and real historical commits from years of independent development).
- `package.json`-based component discovery — correctly found `user-management-api`/`user-management-frontend` (flat, no prefix), `services/auth-service` etc. (nested, `services/` prefix — the original shape), and `agents/linkedin-cover-generator` (nested, `agents/` prefix — a third, previously-unseen naming convention) with the exact same unmodified code.
- The "probability stays `UNKNOWN`, never fabricated" and "no validation → `ESCALATE`, never silently approve" invariants — held in every single run across all five repositories now tested (`social-media-mini`, `user-management-app`, `ai-agents`, `langgraph-demo`, plus the CI fixture).

## Required Product Changes (only what this experiment justifies)

1. **Extend file-extension scanning to include `.ts`/`.tsx`** in `build_impact_assessment()` and `discovery.find_middleware_usages()`. Directly justified: this is the single change that would have let `ai-agents`' real bug fix be evaluated at all.
2. **After (1), re-run a fresh held-out test using a genuinely in-scope repository** (TypeScript or JavaScript, Express-style HTTP framework) not used during this milestone's development — this milestone's held-out selection, constrained by what was available and appropriate to test, landed entirely *outside* the discovery mechanism's scope by coincidence, so it has not yet produced a positive test of generalization to an unseen but in-scope repository.

Explicitly not justified by this experiment: support for non-Node ecosystems, a real AST parser (the regex-based approach correctly handled three distinct real directory conventions and two distinct route-registration receivers without modification), or any change to `RiskAssessment`, `ValidationDecision`, or the recommendation policy.

## Recommendation

**`NEEDS_MORE_WORK`**

Not `PRODUCT_BOUNDARY_IDENTIFIED`: the held-out failures are a narrower-than-documented scope (missing TypeScript), not a fundamental ceiling on the discovery approach itself — the same regex-based mechanism handled a third, previously-unseen component-directory convention (`agents/<name>/`) and a new route-registration pattern correctly on the very same run where it also correctly, honestly declined to guess about content it wasn't built to read.

Not `READY_FOR_BROADER_PILOT`: this milestone has not yet produced a held-out test of generalization to an *in-scope* unseen repository — both held-out repositories fell outside scope, for two different reasons. That specific test — the one this whole process exists to run — is still outstanding.

`NEEDS_MORE_WORK` is the accurate label: extend scanning to TypeScript (a small, mechanical, well-understood change to two file-extension filters, not a redesign), then repeat the held-out procedure — freeze again, select a fresh unseen but in-scope repository, run unmodified, report honestly — before this capability is presented as validated for broader pilot use.

---

## Summary for the Business Owner

- **Branch:** `feature/adapt-architecture-discovery`
- **Latest commit:** `d958a15` (freeze commit; no commits made after held-out selection, per the mandatory ordering)
- **Tests:** 42 automated tests, all passing (19 discovery unit tests, 7 known-repo-shape regression tests, 16 prior decision-policy tests unchanged, plus the new generic-path-guard tests)
- **Known repositories:** `social-media-mini`, `user-management-app` — all recorded acceptance criteria now pass
- **Held-out repositories:** `ai-agents` (2 real historical changes), `langgraph-demo` (1 real historical change) — both correctly, honestly identified as (partially) out of the discovery mechanism's actual scope; zero fabrication, zero crashes
- **Pass/fail summary:** known-repository regression 4/4 pass; held-out repositories 3/3 produced honest, non-fabricated results, but 0/3 produced a positive demonstration of in-scope generalization (none of the three held-out changes were in-scope)
- **Known limitations:** TypeScript (`.ts`/`.tsx`) is not scanned at all (newly discovered this milestone); non-Express message/route registration conventions are not recognized (by design, previously disclosed); non-Node ecosystems are entirely out of scope (by design, previously disclosed)
- **Repository-specific rules added:** **NO** — verified by inspection of every diff in this branch; every new code path is a general mechanism (package.json presence, any-receiver route calls, exported-name usage), with zero references to `social-media-mini`, `user-management-app`, `ai-agents`, `langgraph-demo`, or any specific filename or route path anywhere in `discovery.py` or `analyze_change.py`
- **Recommendation:** `NEEDS_MORE_WORK` — extend to TypeScript, then repeat this exact held-out procedure against a fresh, in-scope, previously-unseen repository before considering broader pilot distribution
