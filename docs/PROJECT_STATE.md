# Project State (operational handoff)

**Read this first.** This is the compact, durable handoff for continuing
ImpactTestAI's engineering. The repository — not prior chat history —
is the source of truth. Consult the documents linked in §9 only when a
specific question requires their detail; do not reconstruct history
from a previous conversation.

## 1. Current repository state

- `main` SHA: **`ce6222c4955755f50f2d586ca7518b5d0e273cc1`**
- `TOOL_VERSION` on `main`: **`0.11.0-pilot`**
- `POLICY_VERSION` on `main`: **`repo-plus-ci-plus-cross-service-plus-discovery-v9`**
- Test count on `main`: **124/124 passing** (`python3 -m pytest slice/tests/ -q`)
- Most recent/active branch: **`feature/workspace-aware-install`**
  (pushed, PR not yet opened/merged — see §6). Bumps `TOOL_VERSION` to
  `0.12.0-pilot` and adds 11 tests (135 total) once merged. Do not treat
  `0.12.0-pilot`/135 as `main`'s current state until that branch is
  actually merged — verify via `git log -1` and the test count before
  relying on either number.

## 2. Product definition (see `docs/PRODUCT_VALIDATION_SPEC.md` for full detail)

**Promises:** direct/middleware-dependency/transitive impact discovery
from real repository evidence (route registrations, imports, mount
prefixes); execution of the component's real, pre-existing `npm test`
(never synthesized); optional, clearly-separated real GitHub Actions CI
history as additional evidence.

**Explicitly does not promise:** complete call-graph analysis (impact
discovery is one hop plus composed mount prefixes, not full graph
traversal); universal framework understanding (Express-style
`receiver.method(path, ...)` convention only — no NestJS decorators,
no non-Node frameworks); that missing CI history means no CI exists
(a repo-wide 100-run window can miss a real, lower-frequency workflow);
automatic diagnosis of ambiguous environment failures (a `FAILED`
never gets an auto-inferred cause); treating insufficient evidence as
a pass.

**Top-level decisions** (`final_recommendation()`):
- **`ACCEPT`** — validation passed and risk/confidence are acceptable.
  **Structurally unreachable under the current policy** —
  `probability_confidence` is hardcoded `"LOW"` in every
  `build_risk_assessment()` call, and overall confidence is always the
  weakest of three dimensions, so it is always `LOW`. This is a
  deliberate, disclosed conservative policy choice, not a bug — do not
  "fix" it without an explicit, separate product/policy decision.
- **`REQUIRE_ADDITIONAL_VALIDATION`** — evidence isn't strong enough to
  clear the change alone (this is the outcome for every clean, fully
  passing run today, given `ACCEPT`'s unreachability above).
- **`ESCALATE`** — at least one validation `FAILED`/`INCONCLUSIVE`, or
  none ran at all. Always wins over a low risk level.

**Validation-level outcomes** (one executed command):
`PASSED` (real, unmodified pass) / `FAILED` (real, unmodified non-zero
exit — never auto-classified as to cause) / `INCONCLUSIVE` (validation
timeout, `npm install` timeout/failure, or equivalent infrastructure
condition — always forces `ESCALATE`, never silently softened).

## 3. Completed milestones (chronological)

| Milestone | Resulting version | Outcome |
|---|---|---|
| Stage 1 → `ADAPT_ARCHITECTURE_DISCOVERY` v5–v9 → `ARTIFACT_HISTORY` | pre-`0.7.0-pilot` era | Evidence-based component/route discovery replacing hardcoded layout assumptions; immutable per-run artifact history. Both accepted, tagged on `main`. |
| Repository hygiene (4 HIGH findings fixed) | — | Stale docs corrected; no behavior change. |
| `0.8.0-pilot` — configurable validation timeout | `0.8.0-pilot` | `--validation-timeout-seconds` replaces a hardcoded 180s literal; default unchanged. |
| `0.9.0-pilot` — pipeline fail-safe | `0.9.0-pilot` | Two real, previously-crashing paths (`npm install` `TimeoutExpired`, CI-history `IncompleteRead`) now fail safely as `INCONCLUSIVE`/`UNKNOWN` instead of crashing the process. |
| `0.10.0-pilot` — generic CI workflow discovery | `0.10.0-pilot` | Hardcoded `.github/workflows/ci.yml` match replaced with a generic `.github/workflows/` prefix check; fixes real filename-mismatch cases. |
| Repository organization (PR #4) | — | Product/docs/pilot-evidence separated into `slice/`, `docs/`, `pilot/`, `artifacts/`. |
| Product Validation Spec (PR #5) | — | `docs/PRODUCT_VALIDATION_SPEC.md` — the current product contract (§2 above). |
| Product validation pilot (PR #6) + gap disposition (PR #7) | — | Fresh 5-repo pilot round; verdict **READY WITH KNOWN LIMITATIONS**; identified and ranked two real gaps (route-label composition, workspace-aware install — see §5, §6). |
| `0.11.0-pilot` — route-label composition (PR #8) | `0.11.0-pilot` | **Merged, current `main` state.** See §5. |

## 4. Deferred findings (remain deferred — do not reopen without an explicit new instruction)

| Finding | Conclusion | Disposition |
|---|---|---|
| CI window crowd-out (a repo-wide 100-run fetch can miss a real, lower-frequency workflow) | Real but rare (1 of 4 sampled repos); fixing it costs far more API calls, worsening the already-tight rate limit | **DEFER.** Investigation kept on branch `investigate/ci-window-crowd-out`, never merged. |
| Environment/setup failure classification (is a `FAILED` really an environment problem, not a defect?) | A safe, generic signal exists only for the narrow "suite failed to load" shape; the more common shape (env failure silently caught, surfaces as an ordinary per-test failure) is indistinguishable from a real defect without repo-specific knowledge | **DEFER.** Investigation kept on branch `investigate/environment-failure-classification`, never merged. |
| Indirect auth/middleware discovery (Passport strategies, NestJS guards, OAuth call-expression middleware) | Real misses exist, but every generic mechanism considered is either unbounded (explodes false positives) or requires framework-specific special-casing; one candidate fix was also shown to produce a live, real false positive on the same evidence | **DEFER.** Investigation kept on branch `investigate/indirect-auth-discovery`, never merged. |
| CI rate-limit mitigation | Not separately investigated; repeatedly confirmed as a real, binding constraint (unauthenticated GitHub API, 60 req/hour) by every CI-history-related investigation and pilot round | **Remains deferred.** |
| Retries (for flaky validation results) | Not implemented; explicitly excluded from every fail-safe/timeout milestone | **Remains deferred.** |
| `ACCEPT` policy reachability | Documented as a deliberate, disclosed characteristic (§2); revisiting it is a product/policy decision, not an engineering fix | **Remains deferred** pending an explicit product decision. |
| Broader risk-model changes | Not investigated as part of any specific milestone; explicitly out of scope for every implementation milestone to date | **Remains deferred.** |

**None of the above should be re-investigated or implemented without an explicit, new engineering instruction naming it.**

## 5. Resolved product gaps

- **Route-label / mount-prefix composition** (`0.11.0-pilot`, merged to
  `main` as part of PR #8, commit `ce6222c`). Real pilot finding: three
  distinct real routes (`GET /`, `GET /api/v1`, `GET /api/v1/emojis`)
  were all rendered as an identical `GET /` label, and the same root
  cause made a route's own real, passing test coverage invisible.
  Fixed via `discovery.build_mount_map()`/`compose_route_path()`,
  composing `receiver.use(prefix, target)` mount registrations —
  reusing existing import-resolution primitives, no new discovery
  mechanism, no repository-specific heuristics.
- **Validated real-world**, on two independent repositories
  (`w3cj/express-api-starter` — the original pilot fixture; the fix
  also caught and repaired a real, unrelated bug in import-path
  resolution along the way, found via `hagopj13/node-express-boilerplate`):
  the three routes are now distinct, and previously-uncredited test
  coverage is now correctly attributed.

## 6. Current milestone: workspace-aware validation installation

- **Why it exists:** real pilot finding (Case 3 of the 2026-08-29 pilot
  round) — `socketio/socket.io`'s `packages/socket.io-parser` package
  failed validation with `FAILED`, exit 127, `prettier: command not
  found`, because `npm install` ran only inside the component's own
  directory while `prettier` is a devDependency this npm-workspaces
  repository hoists to its root.
- **Intended narrow rule:** if the changed component is a declared
  member of an npm/Yarn workspace (an ancestor `package.json`'s
  `"workspaces"` field lists it, matched pattern-by-pattern — the
  standard field both npm and Yarn read, not a heuristic), `npm
  install` runs at that workspace root instead of inside the component
  alone. Only the install command's `cwd` changes; the validation/test
  command itself is unchanged. No workspace detected → byte-for-byte
  prior behavior. pnpm's separate `pnpm-workspace.yaml` is an explicit,
  disclosed non-goal.
- **What has been implemented:** `discovery.find_workspace_root()` (plus
  two small pattern-matching helpers) and the `run_validation()`
  integration, fully committed. 11 new tests (8 discovery-level, 3
  analyze_change-level: positive workspace case, non-workspace control
  case, genuine-install-failure case). `TOOL_VERSION` bumped to
  `0.12.0-pilot`. Full design (`docs/decisions/WORKSPACE_AWARE_INSTALL_DESIGN.md`,
  written before implementation, answers all 7 required design
  questions) and completion evidence
  (`docs/decisions/WORKSPACE_AWARE_INSTALL_DISPOSITION.md`) are both
  written and committed.
- **Current branch/commit:** `feature/workspace-aware-install` @
  `ede1ee1`. Pushed to origin. **No PR has been opened yet** — this
  session cannot open PRs itself (no `gh` CLI, no token, no
  authenticated browser in this environment); a human must open one at
  `https://github.com/venusabhay/ImpactTestAI/compare/main...feature/workspace-aware-install`.
- **What remains unverified:** 135/135 tests pass locally and the core
  fix is directly confirmed real-world (a warm-`node_modules` re-run
  against the exact pilot repository/commit shows `prettier --check`
  now running and passing, where it previously failed with "command not
  found"). What has **not** been independently confirmed is the
  package's full `mocha` test suite completing end-to-end on this
  development machine — blocked by an unrelated issue (next bullet).
  `pilot-ci.yml` has not yet run against this branch's exact head SHA
  (no PR open yet); that must happen, and be green, before considering
  a merge.
- **Unrelated fixture issue — do not fix as part of this milestone:**
  `packages/socket.io-parser/postcompile.sh` in the real
  `socketio/socket.io` repository runs `sed -i '/debug(/d' ...` — valid
  on GNU sed (Linux, where this repository's own real CI runs), but
  BSD/macOS `sed` requires an explicit argument after `-i`, so it fails
  on a macOS development machine. **This is a pre-existing, unrelated
  target-repository/platform portability defect, not a defect in this
  analyzer or in the workspace-install fix.** It must not be "fixed" —
  no `sed` shim, no build-script edit, no environment workaround — as
  part of this or any future milestone unless a human explicitly
  decides to address it as its own, separately-scoped task.
- **Current merge decision:** **not yet merged.** The single next
  action (§8) is to complete the standard review/verification gate
  (open PR → verify `pilot-ci.yml` on the exact head SHA → review diff
  scope → merge only if green → re-run the suite and the real pilot
  case on post-merge `main`) before deciding whether to merge.

## 7. Engineering operating rules (standing, established across this entire project)

- No repository-specific heuristics, filenames, or hardcoded
  dependency/package names in any discovery or validation mechanism.
- No opportunistic fixes: an unrelated defect found during a milestone
  is documented, not fixed, unless a human explicitly scopes a
  separate task for it.
- No risk/confidence/recommendation-policy changes, and no
  `POLICY_VERSION` change, unless a human explicitly authorizes it as
  its own decision — never as a side effect of an unrelated fix.
- No `.github/workflows/` changes unless explicitly authorized.
- Investigations do not automatically become implementation work — an
  investigation ends in PROCEED/DEFER/(rarely) INVESTIGATE FURTHER, and
  only an explicit follow-up instruction turns a PROCEED into a coded
  milestone.
- Pilot/verification evidence must come from real repositories and real
  commits — never manufactured or synthetic outcomes chosen to fit a
  hypothesis.
- Never fabricate evidence anywhere in the tool's own output (this is
  also the core product philosophy, not just a process rule).
- Preserve raw evidence (real stdout/stderr, exact exit codes, exact
  commit SHAs) when reporting findings — don't summarize away the
  original error.
- Keep implementation scope narrow — a design doc's own explicit
  "what this does not do" section is binding, not aspirational.
- Delivery process for every change: feature/investigation/docs branch
  from `main` → implement → full test suite → real-world verification
  where applicable → commit and push → a human opens the PR (this
  session cannot) → verify `pilot-ci.yml` on the **exact** PR head SHA
  → review diff for scope/policy/workflow creep → merge only if green
  → re-run the full suite (and any relevant real pilot case) on
  post-merge `main`.

## 8. Current next action

**Complete the review/verification gate for the workspace-aware
installation implementation (`feature/workspace-aware-install` @
`ede1ee1`) before deciding whether to merge it** — a human needs to
open the PR; then verify `pilot-ci.yml` on that exact head SHA, review
the diff for scope, and merge only if green, per §7's standing process.

Do not start a new backlog item, investigation, or milestone before
this gate is resolved.

## 9. Authoritative documents (consult by reference, not by copying)

- [`docs/PRODUCT_VALIDATION_SPEC.md`](PRODUCT_VALIDATION_SPEC.md) — the
  product contract (§2 above summarizes it).
- [`docs/decisions/`](decisions/) — one document per engineering
  decision; in particular
  [`PRODUCT_VALIDATION_GAP_DISPOSITION.md`](decisions/PRODUCT_VALIDATION_GAP_DISPOSITION.md)
  (already on `main`). `WORKSPACE_AWARE_INSTALL_DESIGN.md` and
  `WORKSPACE_AWARE_INSTALL_DISPOSITION.md` exist only on the unmerged
  `feature/workspace-aware-install` branch (§6) — not yet on `main`, so
  not linked here; read them from that branch until it merges.
- [`pilot/reports/2026-08-29-product-validation-pilot.md`](../pilot/reports/2026-08-29-product-validation-pilot.md) —
  the fresh pilot round that motivated both the route-label-composition
  and workspace-aware-install milestones.
- `pilot/investigations/` — evidence for each deferred finding in §4
  (note: several investigations live only on their own unmerged
  `investigate/...` branches, per the project's rule that investigation
  branches stay separate from `main` unless they lead to an
  implementation).
- [`PILOT.md`](../PILOT.md) — the non-technical, user-facing guide to
  actually running the pilot.
