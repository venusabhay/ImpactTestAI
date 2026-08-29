# Project State (operational handoff)

**Read this first.** This is the compact, durable handoff for continuing
ImpactTestAI's engineering. The repository — not prior chat history —
is the source of truth. Consult the documents linked in §10 only when a
specific question requires their detail; do not reconstruct history
from a previous conversation.

## 1. Current repository state

- `main` SHA: **`e4862fb4c06652c1e8f8af008132152c6fcc42cd`**
- `TOOL_VERSION` on `main`: **`0.13.0-pilot`**
- `POLICY_VERSION` on `main`: **`repo-plus-ci-plus-cross-service-plus-discovery-v9`**
  — unchanged since it was first recorded in this document; no policy
  decision has been made or authorized at any point since.
- Test count on `main`: **145/145 passing** (`python3 -m pytest slice/tests/ -q`)
- **No implementation branch is currently pending merge.** The three
  implementation milestones active or queued as of the last handoff
  (route-label composition, workspace-aware install, and the
  since-added validation-command ancestor fallback) are all merged to
  `main` — see §3/§5.
- **One non-code branch remains pushed but not merged:**
  `pilot/milestone-a-generalization` (evidence report only, no source
  changes) — see §6. Its content directly motivated the now-merged
  validation-ancestor-fallback fix, but the report document itself has
  not been opened as a PR or merged into `main`.
- **No engineering work is currently authorized.** A next milestone
  (Milestone B — Evaluation & Trust) has been recommended but
  explicitly not authorized — see §7. Do not begin it, or any other
  new backlog item, without an explicit instruction naming it.

## 2. Product definition (see `docs/PRODUCT_VALIDATION_SPEC.md` for full detail)

**Promises:** direct/middleware-dependency/transitive impact discovery
from real repository evidence (route registrations, imports, mount
prefixes); execution of the component's real, pre-existing `npm test`
(never synthesized, now including a real ancestor-directory fallback
when the changed component has no test script of its own — see §5);
optional, clearly-separated real GitHub Actions CI history as
additional evidence.

**Explicitly does not promise:** complete call-graph analysis (impact
discovery is one hop plus composed mount prefixes, not full graph
traversal); universal framework understanding (Express-style
`receiver.method(path, ...)` convention only — no NestJS decorators,
no non-Node frameworks); pnpm workspace support (a disclosed boundary,
now confirmed twice — see §4b); that missing CI history means no CI
exists (a repo-wide 100-run window can miss a real, lower-frequency
workflow); automatic diagnosis of ambiguous environment failures (a
`FAILED` never gets an auto-inferred cause); treating insufficient
evidence as a pass.

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
| Product validation pilot (PR #6) + gap disposition (PR #7) | — | Fresh 5-repo pilot round; verdict **READY WITH KNOWN LIMITATIONS**; identified and ranked two real gaps (route-label composition, workspace-aware install). |
| `0.11.0-pilot` — route-label composition (PR #8, merge `ce6222c`) | `0.11.0-pilot` | See §5. |
| `0.12.0-pilot` — workspace-aware validation installation (PR #10, merge `e37bc30`) | `0.12.0-pilot` | See §5. |
| Milestone A — generalization pilot (evidence round; no code change) | — (still `0.12.0-pilot` at the time) | 5 materially different real repositories analyzed against `0.12.0-pilot`; found the validation-command-discovery gap resolved by the next row. See §6. |
| `0.13.0-pilot` — validation-command ancestor fallback (PR #11, merge `e4862fb`) | `0.13.0-pilot` | **Merged, current `main` state.** See §5. |

## 4. Deferred findings (remain deferred — do not reopen without an explicit new instruction)

| Finding | Conclusion | Disposition |
|---|---|---|
| CI window crowd-out (a repo-wide 100-run fetch can miss a real, lower-frequency workflow) | Real but rare (1 of 4 sampled repos); fixing it costs far more API calls, worsening the already-tight rate limit | **DEFER.** Investigation kept on branch `investigate/ci-window-crowd-out`, never merged. |
| Environment/setup failure classification (is a `FAILED` really an environment problem, not a defect?) | A safe, generic signal exists only for the narrow "suite failed to load" shape; the more common shape (env failure silently caught, surfaces as an ordinary per-test failure) is indistinguishable from a real defect without repo-specific knowledge | **DEFER.** Investigation kept on branch `investigate/environment-failure-classification`, never merged. |
| Indirect auth/middleware discovery (Passport strategies, NestJS guards, OAuth call-expression middleware) | Real misses exist, but every generic mechanism considered is either unbounded (explodes false positives) or requires framework-specific special-casing; one candidate fix was also shown to produce a live, real false positive on the same evidence | **DEFER.** Investigation kept on branch `investigate/indirect-auth-discovery`, never merged. |
| CI rate-limit mitigation | Not separately investigated; repeatedly confirmed as a real, binding constraint (unauthenticated GitHub API, 60 req/hour) by every CI-history-related investigation and pilot round — most recently during Milestone A, where this session's own research exhausted the limit before all five repositories could be checked via the API | **Remains deferred.** |
| Retries (for flaky validation results) | Not implemented; explicitly excluded from every fail-safe/timeout milestone | **Remains deferred.** |
| `ACCEPT` policy reachability | Documented as a deliberate, disclosed characteristic (§2); revisiting it is a product/policy decision, not an engineering fix | **Remains deferred** pending an explicit product decision. |
| Broader risk-model changes | Not investigated as part of any specific milestone; explicitly out of scope for every implementation milestone to date | **Remains deferred.** |

**None of the above should be re-investigated or implemented without an explicit, new engineering instruction naming it.** None were reopened by Milestone A or the validation-ancestor-fallback milestone.

## 4b. Documented observations (not formal deferred decisions — recorded, not investigated, not authorized for action)

Distinct from §4: these were noticed as a side effect of Milestone A and the validation-ancestor-fallback milestone's real-world verification, not produced by a dedicated investigation, and have no DEFER/PROCEED disposition of their own. They are observations on record, not backlog items.

- **pnpm `workspace:*` protocol unsupported by `npm install`.** Real evidence: `vitejs/vite`'s root `package.json` declares `"vite": "workspace:*"`; running `npm install` there (which the ancestor-fallback fix now correctly attempts, for the first time, since no prior code path ever reached a real pnpm root) fails with `npm error code EUNSUPPORTEDPROTOCOL`. This is the same, already-disclosed pnpm non-support boundary from the workspace-aware-install milestone, now confirmed a second time from a different angle (validation execution, not install redirection). Handled safely today: an honest `INCONCLUSIVE`/`INFRASTRUCTURE (dependency install failed)`, never fabricated. **Not fixed, not scoped, no expansion of pnpm support has been authorized.**
- **`apache/superset`'s full root-level `jest` suite did not complete within 900 seconds** on the development machine used for verification. Consistent with, not contradicting, other "slow but healthy suite" findings already on record (`fastify`, `opentelemetry-js`'s cold workspace-root install) — real repositories whose validation, once correctly selected, legitimately takes longer than the tool's default timeout window on a single development machine. **No slow-test optimization or default-timeout change has been authorized.**
- **OpenTelemetry build-step observation** (Milestone A Case 1, `open-telemetry/opentelemetry-js`): that repository's real CI runs an explicit, separate `npm run compile` step (not wired through an npm lifecycle hook) before testing, which this analyzer's install-then-test model does not run — plausibly, though not conclusively, the cause of a real local `FAILED` that did not match that commit's real, all-green CI history. Explicitly recorded as insufficiently generalized to justify a fix: `apollographql/apollo-server` (Milestone A Case 5) is real, positive counter-evidence that build-before-test already works correctly today when a repository wires it through `pretest`. **Remains a follow-up observation only, not implemented, not scheduled.**

## 5. Resolved product gaps

- **Route-label / mount-prefix composition** (`0.11.0-pilot`, merged to
  `main` as part of PR #8, commit `ce6222c`). Real pilot finding: three
  distinct real routes (`GET /`, `GET /api/v1`, `GET /api/v1/emojis`)
  were all rendered as an identical `GET /` label, and the same root
  cause made a route's own real, passing test coverage invisible.
  Fixed via `discovery.build_mount_map()`/`compose_route_path()`,
  composing `receiver.use(prefix, target)` mount registrations —
  reusing existing import-resolution primitives, no new discovery
  mechanism, no repository-specific heuristics. Validated real-world on
  two independent repositories (`w3cj/express-api-starter`;
  `hagopj13/node-express-boilerplate`, which also surfaced and let this
  fix repair a real, unrelated import-path-resolution bug along the
  way).
- **Workspace-aware validation installation** (`0.12.0-pilot`, merged
  to `main` as part of PR #10, commit `e37bc30`). Real pilot finding:
  `socketio/socket.io`'s `packages/socket.io-parser` package failed
  validation (`FAILED`, exit 127, `prettier: command not found`)
  because `npm install` ran only inside the component's own directory,
  while `prettier` is a devDependency this npm-workspaces repository
  hoists to its root. Fixed via `discovery.find_workspace_root()`: when
  the changed component is a declared member of an npm/Yarn workspace
  (the standard `"workspaces"` `package.json` field), `npm install`
  runs at that workspace root instead — only the install command's
  `cwd` changes; the validation/test command itself is unchanged; no
  workspace detected → byte-for-byte prior behavior. pnpm's separate
  `pnpm-workspace.yaml` was an explicit, disclosed non-goal from the
  start — see §4b for its since-confirmed real-world edge. Design:
  `docs/decisions/WORKSPACE_AWARE_INSTALL_DESIGN.md`. Disposition:
  `docs/decisions/WORKSPACE_AWARE_INSTALL_DISPOSITION.md`.
- **Validation-command ancestor fallback** (`0.13.0-pilot`, merged to
  `main` as part of PR #11, commit `e4862fb`). Real, converging finding
  from Milestone A (§6): `vitejs/vite` and `apache/superset` both have
  a real changed component with no `"test"` script of its own, while a
  real, meaningful test script — the one their own real CI actually
  runs — exists at a workspace-root or repository-root ancestor;
  validation-command discovery previously only checked the changed
  component's own `package.json`, so both were reported "no validation
  available" and escalated even though real, passing validation
  existed one directory away. Fixed via
  `discovery.find_validation_ancestor()`: when the changed component
  has no test script, the analyzer walks strictly upward through
  already-discovered components and uses the nearest one that has a
  real `"test"` script — deliberately independent of
  `find_workspace_root()` (both real motivating repositories fall
  outside that function's declared-workspace-membership rule). A
  component with its own valid local command is completely unaffected;
  when no ancestor qualifies either, the existing rejection/`ESCALATE`
  behavior is unchanged, byte-for-byte. Re-verified end-to-end against
  both real repositories post-fix: discovery/selection is now correct
  on both; execution reached honest `INCONCLUSIVE` outcomes on both,
  for two separate, pre-existing reasons now recorded in §4b, neither a
  defect in this fix. Design:
  `docs/decisions/VALIDATION_ANCESTOR_FALLBACK_DESIGN.md`. Disposition:
  `docs/decisions/VALIDATION_ANCESTOR_FALLBACK_DISPOSITION.md`.

## 6. Milestone A — generalization pilot (completed evidence round)

- **Objective:** across five real repositories materially different
  from every repository used in this project's prior investigations
  and pilot rounds, how accurately does ImpactTestAI `0.12.0-pilot`
  identify relevant impact/test scope, where does it fail, and where
  is it uncertain? An evaluation round, not an implementation
  milestone — no product behavior was changed to produce it.
- **Sample:** `open-telemetry/opentelemetry-js` (large npm-workspaces
  monorepo), `vitejs/vite` (pnpm-workspace monorepo — the disclosed
  package-manager boundary), `apache/superset` (polyglot Python+JS,
  real commit touching both), `nodejs/undici` (single-package,
  GitHub Actions version×OS matrix CI), `apollographql/apollo-server`
  (small npm-workspaces monorepo with real internal consumers,
  CircleCI rather than GitHub Actions) — selected against an explicit
  diversity matrix before outcomes were known.
- **Outcome:** component/route discovery, the pnpm non-support
  boundary, and the workspace-install redirect all generalized
  correctly to repositories substantially larger/more complex than
  anything previously used to build or verify them; nothing fabricated
  in any of the five cases. One real, converging gap found
  (validation-command discovery had no ancestor fallback — independently
  reproduced in 2 of 5 repositories) and, per explicit follow-on
  instruction, fixed as the `0.13.0-pilot` milestone (§5). A second,
  lower-confidence observation (the OpenTelemetry build-step
  observation) was explicitly deferred rather than acted on — see §4b.
- **Report location:** `pilot/reports/2026-08-29-milestone-a-generalization.md`
  and `docs/decisions/MILESTONE_A_SELECTION_RECORDS.md`. **These exist
  only on the pushed, never-PR'd branch `pilot/milestone-a-generalization`
  — not on `main`.** The evidence they contain was already fully acted
  on (it is what produced §5's validation-ancestor-fallback fix and
  §4b's observations), but the report document itself has not been
  merged. Read it from that branch until/unless a human opens a PR for
  it; do not treat its absence from `main` as evidence the round didn't
  happen.

## 7. Recommended next milestone — Milestone B: Evaluation & Trust (recommended, NOT authorized)

**This is a recommendation on record, not an authorization. Do not
begin any part of it without an explicit instruction to do so.**

- **Proposed objective:** move from "we have fixed several real
  problems" to "we can quantitatively demonstrate how reliable the
  product is" — build a reusable evaluation corpus from the real
  repositories/cases already accumulated across every pilot round and
  Milestone A, then measure, systematically rather than case-by-case:
  correct impact/test selection; false positives; false negatives;
  `INCONCLUSIVE` decisions; environment failures kept distinct from
  analyzer failures; validation-command-discovery success rate;
  explanation/evidence quality; analyzer runtime; any measurable
  CI/test-execution savings.
- **Proposed exit criterion:** a defensible baseline of ImpactTestAI's
  accuracy, uncertainty, failure modes, and potential business value
  across a representative historical evaluation set — the point at
  which a business/product decision (reliability work, CI integration,
  cost reduction, broader repository support, or a controlled beta)
  can be made from measurements rather than accumulated anecdotes.
- **Explicitly not to be picked up as part of this milestone unless the
  evaluation itself demonstrates they are necessary:** pnpm
  `workspace:*` support expansion; general build-step inference;
  slow-test optimization; CI rate-limit/retry work; broader risk-model
  changes; any of the seven §4 deferred items. These remain known
  observations, not automatic priorities.
- **Status:** recommended by product/engineering leadership at the
  close of the `0.13.0-pilot` milestone. **Not yet authorized.** No
  corpus construction, no measurement tooling, and no other engineering
  action toward this milestone should begin until it is.

## 8. Engineering operating rules (standing, established across this entire project)

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
  milestone. A recommendation (see §7) is not authorization either.
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

## 9. Current next action

**None authorized.** `0.13.0-pilot` is cleanly closed: merged, tested
(145/145), CI-green on the merge commit, and post-merge-verified. §4b's
observations and §4's deferred items stay exactly as they are. Milestone
B (§7) is recommended but not authorized and must not be started from
this document alone. If a specific instruction arrives, act on that
instruction; otherwise, no engineering work — implementation,
investigation, or corpus-building — should begin from this handoff.

## 10. Authoritative documents (consult by reference, not by copying)

- [`docs/PRODUCT_VALIDATION_SPEC.md`](PRODUCT_VALIDATION_SPEC.md) — the
  product contract (§2 above summarizes it).
- [`docs/decisions/`](decisions/) — one document per engineering
  decision; in particular
  [`PRODUCT_VALIDATION_GAP_DISPOSITION.md`](decisions/PRODUCT_VALIDATION_GAP_DISPOSITION.md),
  [`WORKSPACE_AWARE_INSTALL_DESIGN.md`](decisions/WORKSPACE_AWARE_INSTALL_DESIGN.md)/
  [`DISPOSITION.md`](decisions/WORKSPACE_AWARE_INSTALL_DISPOSITION.md), and
  [`VALIDATION_ANCESTOR_FALLBACK_DESIGN.md`](decisions/VALIDATION_ANCESTOR_FALLBACK_DESIGN.md)/
  [`DISPOSITION.md`](decisions/VALIDATION_ANCESTOR_FALLBACK_DISPOSITION.md)
  — all now on `main`.
  [`MILESTONE_A_SELECTION_RECORDS.md`](decisions/MILESTONE_A_SELECTION_RECORDS.md)
  exists only on the unmerged `pilot/milestone-a-generalization` branch
  (§6) — not linked from `main`-relative paths until that branch
  merges.
- [`pilot/reports/2026-08-29-product-validation-pilot.md`](../pilot/reports/2026-08-29-product-validation-pilot.md) —
  the fresh pilot round that motivated both the route-label-composition
  and workspace-aware-install milestones.
- `pilot/reports/2026-08-29-milestone-a-generalization.md` — the
  generalization round (§6). **On the unmerged
  `pilot/milestone-a-generalization` branch only**, not on `main`.
- `pilot/investigations/` — evidence for each deferred finding in §4
  (note: several investigations live only on their own unmerged
  `investigate/...` branches, per the project's rule that investigation
  branches stay separate from `main` unless they lead to an
  implementation).
- [`PILOT.md`](../PILOT.md) — the non-technical, user-facing guide to
  actually running the pilot.
