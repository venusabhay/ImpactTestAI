# Milestone A — Generalization Pilot — 2026-08-29

**Objective:** across five real repositories materially different from
every repository used in this project's prior investigations and
pilot rounds, how accurately does ImpactTestAI `0.12.0-pilot` identify
relevant impact/test scope, where does it fail, and where is it
uncertain?

**Not an implementation milestone.** No product behavior was changed
to produce this round. `TOOL_VERSION`/`POLICY_VERSION` unchanged
(`0.12.0-pilot`/`repo-plus-ci-plus-cross-service-plus-discovery-v9`)
throughout — confirmed on `main` @ `e37bc30` before this round began
and again after. 135/135 tests pass, confirmed both times. Every case
below used the analyzer exactly as a pilot user would invoke it per
[`PILOT.md`](../../PILOT.md) (`--npm-install`, `--github-repo`), with
one environment-only accommodation: `--node-bin` pointed at a working
local Node install, because the default `node` on the analysis
machine's `PATH` (a stray, unrelated local Node 25 install) currently
segfaults on launch — an existing, documented, sanctioned flag for
exactly this situation, not a new capability, and irrelevant to any
repository analyzed.

## Sample and selection rationale

5 real, active, public repositories, selected against an explicit
diversity matrix (ecosystem, package manager, repository structure,
dependency topology, CI architecture, test organization) **before**
their analysis outcomes were known. None was chosen because a
particular result was expected or desired, and none was modified to
produce a particular outcome. Full selection records — including why
each candidate was chosen over alternatives that were checked and
rejected — are in
[`docs/decisions/MILESTONE_A_SELECTION_RECORDS.md`](../../docs/decisions/MILESTONE_A_SELECTION_RECORDS.md).

| # | Repository | Real commit | Profile |
|---|---|---|---|
| 1 | `open-telemetry/opentelemetry-js` | `61126358cb` — `fix(sdk-metrics): ignore infinity in exponential histograms` (#7015) | Large npm-workspaces monorepo (40+ packages) |
| 2 | `vitejs/vite` | `ee644014aa` — `chore: delete unused PluginContainerOptions` (#23382) | pnpm-workspace monorepo — the disclosed package-manager boundary |
| 3 | `apache/superset` | `de33efae98` — `fix(table-chart): support where for adhoc columns with server-side pagination` (#42706) | Polyglot: Python backend + npm-workspace JS frontend, real commit touching both |
| 4 | `nodejs/undici` | `fc3450dcf1` — `fix(socks5-proxy-agent): destroy socket when negotiation times out` (#5709) | Single-package repo, GitHub Actions version×OS matrix CI |
| 5 | `apollographql/apollo-server` | `3f46c51d0f` — `fix(deps): remove vulnerable dependency uuid` (#8201) | Small npm-workspaces monorepo with real internal/indirect consumers, CircleCI (not GitHub Actions) |

No case was manufactured to produce a failure or a pass. Every result
below is what the analyzer actually produced on the first real run
against the real repository at the real commit.

A repeated, unplanned constraint shaped how independent evidence was
gathered: the unauthenticated GitHub REST API's 60-request/hour ceiling
was exhausted partway through repository selection (by this session's
own research, not by the analyzer) and did not reset for the rest of
this round. Every check-run/CI comparison for candidates 2-5 below was
gathered by reading the public GitHub web UI directly (PR "Checks"
tabs, commit pages) instead of the REST API used for candidate 1. This
is reported as a real, first-hand recurrence of the already-deferred
"CI rate-limit mitigation" item (see `PROJECT_STATE.md` §4), not a new
finding — but it is worth naming plainly: **a pilot user doing exactly
this kind of multi-repository review, by hand or via this tool, will
hit the same wall within about an hour of unauthenticated use.**

## Per-case results

### Case 1 — `open-telemetry/opentelemetry-js`, `61126358cb`

- **What the analyzer found:** correctly identified `packages/sdk-metrics`
  as the changed component (real, deep workspace path:
  `packages/sdk-metrics/src/aggregator/ExponentialHistogram.ts`), and
  separately identified the repository root itself as a second changed
  component (`CHANGELOG.md` was also touched by this commit). Correctly
  found **zero** route/middleware relationship for an SDK-shaped
  package — honestly disclosed via `IMPORTANT UNKNOWNS`.
- **Workspace-aware install generalized correctly:** the report records
  `install ran at workspace root: .` for the `sdk-metrics` validation —
  confirming the 0.12.0-pilot milestone's workspace-root install logic
  correctly detects and redirects on a real monorepo with five
  workspace glob patterns and dozens of packages, materially larger and
  deeper than either repository used to build and verify that
  milestone (`socketio/socket.io`, `hagopj13/node-express-boilerplate`).
- **Validation result:** both selected validations (`sdk-metrics`,
  and the root component) **FAILED** — real, reproducible
  `ERR_UNSUPPORTED_DIR_IMPORT` errors, e.g.:
  ```
  Exception during run: Error: Directory import '.../packages/sdk-metrics/src'
  is not supported resolving ES modules imported from
  .../test/aggregator/Drop.test.ts
  ```
  Reproduced identically via direct `npx mocha` invocation (bypassing
  the analyzer entirely) on two different local Node major versions
  (22 and 24) — not a fluke of the analyzer's own subprocess handling.
- **Ground truth:** the real GitHub Actions history for this exact
  commit shows **44/44 check-runs `success`**, including a
  `node-tests` matrix across Node 18/18.19/20/20.6/22/24/26,
  `browser-tests`, `webworker-tests`, `e2e-tests`, `lint`, and
  `peer-api-check`, all on `ubuntu-latest`.
- **Classification: environmental limitation, not a confirmed analyzer
  defect.** The real repository's own CI workflow
  (`.github/workflows/unit-test.yml`) runs three phases — install,
  then a *separate, explicit* `npm run compile` (`tsc --build`) step,
  then a Node-version switch before `npm test` — and only after that
  build step does it run tests. The analyzer's validation model is
  install-then-test; it does not know to run an unrelated `compile`
  script first unless that script is wired into `test` via an npm
  lifecycle hook (`pretest`). This repository does not wire it that
  way. Case 5 below shows a repository where the identical shape of
  problem (compile-before-test) is wired via `pretest` and the
  analyzer's real run succeeds cleanly — strong converging evidence for
  this specific explanation. The analyzer behaved exactly as designed
  throughout: it ran the real, unmodified command, reported a real
  `FAILED`, explicitly declined to guess a cause
  (`classification: Unknown / insufficient evidence -- requires human
  triage`), and escalated rather than fabricating a pass.
- **Candidate gap surfaced:** *the analyzer's validation model assumes
  `npm install` followed by the selected test command is sufficient;
  at least one real, active repository requires a separate, explicit
  build/compile step in between that is not wired into any npm
  lifecycle hook.* Not implemented here — evidence only, per this
  milestone's fix policy.

### Case 2 — `vitejs/vite`, `ee644014aa`

- **What the analyzer found:** correctly identified `packages/vite` as
  the sole changed component (single-file diff, no root-level file
  touched by this commit). Correctly found **zero** route/middleware
  relationship (a bundler internals file, honestly disclosed).
- **Package-manager boundary held correctly:** `packages/vite`'s
  ancestor `package.json` has no `"workspaces"` field anywhere in this
  repository — workspace membership here is declared only via
  `pnpm-workspace.yaml`, the format 0.12.0-pilot's design doc
  explicitly, disclosedly does not read. `find_workspace_root()`
  correctly returned no redirect; install ran exactly where it always
  would have (`packages/vite`), byte-for-byte the pre-0.12.0-pilot
  behavior. The disclosed pnpm boundary held on a real, large,
  active pnpm-only repository, not just the unit-test corpus.
- **Validation result:** `NOT AVAILABLE: INTEGRATION_TEST for 'vite' --
  No 'test' script found for component 'vite' (no package.json test
  script)`. **No validation was executed. Decision: ESCALATE.**
- **Ground truth, verified directly:** `packages/vite/package.json`
  genuinely has no `"test"` script — confirmed by reading the real
  file (its `scripts` are `dev`/`build`/`build-bundle`/`build-types`/
  `typecheck`/`lint`/`format`/`generate-target`/`prepublishOnly`, no
  `test`). All real testing for this repository is defined **only** at
  the repository root: `"test": "pnpm test-unit && pnpm test-serve &&
  pnpm test-build"`. The real PR (#23382) triggered exactly one
  relevant CI workflow, `CI` (`on: pull_request`), which runs that
  root-level suite; it passed ("20 of 21 checks passed" at merge).
- **Classification: false negative (real coverage gap), not an
  honesty failure.** The analyzer did not fabricate anything — it
  correctly reported no validation was available for the component it
  found. But real, meaningful validation for this exact change *did*
  exist and *did* run in the real repository's CI; the analyzer never
  looked for it, because it only checks the changed component's own
  `package.json` for a `test` script, with no fallback to an ancestor
  directory's script when the immediate component has none.

### Case 3 — `apache/superset`, `de33efae98`

- **What the analyzer found:** correctly identified
  `superset-frontend/plugins/plugin-chart-table` as the changed
  component — a real JS/TS package nested three directories deep
  inside a 10,000+-file polyglot repository, discovered correctly
  despite the depth and the surrounding non-JS structure. This commit
  is genuinely polyglot: it also touches `superset/models/helpers.py`
  (Python) and a Python test file. **The analyzer said nothing at all
  about the Python change** — correct, disclosed ecosystem-boundary
  behavior, not a silent gap: this tool has never claimed Python
  support, and it did not fabricate anything resembling route or
  component evidence for it.
- **Validation result:** `NOT AVAILABLE: INTEGRATION_TEST for
  '@superset-ui/plugin-chart-table' -- No 'test' script found` (its
  `package.json` `scripts` object is genuinely empty — confirmed by
  reading the real file). **No validation was executed. Decision:
  ESCALATE.**
- **Ground truth:** the real PR (#42706) triggered 80 named CI jobs,
  including a real, component-relevant `Frontend Build CI (unit tests,
  linting & sanity checks)` job defined at `superset-frontend/`'s own
  root (`"test": "cross-env NODE_ENV=test ... jest ..."`), which ran
  and was required to merge.
- **Classification: the same false negative as Case 2, independently
  reproduced in a structurally unrelated repository.** Two of five
  materially different real repositories hit the identical gap shape:
  a real, deeply-nested changed component with no `test` script of its
  own, sitting under a real ancestor workspace root that does have one
  and whose script is what real CI actually runs. This is no longer a
  single-repository anecdote.

### Case 4 — `nodejs/undici`, `fc3450dcf1`

- **What the analyzer found:** correctly identified `undici` (a
  single-package, non-workspace repository) as the sole component,
  correctly ran its real `npm test`, and correctly found no
  route/middleware relationship for a low-level dispatcher-agent file
  (honestly disclosed).
- **Validation result:** `npm test` **FAILED** (exit 1) — the full
  suite (1518 tests across 134 suites) ran 1514 passed / 0 failed / 1
  cancelled, then one specific, unrelated test
  (`test/sync-error-in-callback.js`) hit its own internal 180-second
  per-test timeout. `classification: Unknown / insufficient evidence --
  requires human triage` (the analyzer, correctly, did not guess a
  cause). **Decision: ESCALATE.**
- **Ground truth:** at merge time, PR #5709 showed "36 of 38 checks
  passed." Independently, a **later, real, maintainer-triggered re-run
  of the exact same PR's CI** (`mcollina`, `undici@5474255`) was
  checked directly on GitHub Actions and shows genuine flakiness: "4
  errors and 256 notices," including a *different* test
  (`test/interceptors/cache.js:3157`, a stale-while-revalidate cache
  assertion) failing on `Test with Node.js 26 on macos-latest`.
- **Classification: environmental limitation, not an analyzer defect.**
  Two independent real executions of this repository's own test suite
  (the analyzer's local run, and a maintainer's own CI re-run) each
  hit a real, different, unrelated test failure. This is convergent,
  independent evidence that `nodejs/undici`'s real test suite has
  genuine, pre-existing, environment-sensitive flakiness — not
  something introduced by, or specific to, this analysis. The analyzer
  again did exactly what it is designed to do: ran the real command,
  reported the real result, declined to guess, escalated.

### Case 5 — `apollographql/apollo-server`, `3f46c51d0f`

- **What the analyzer found:** correctly identified `packages/server`
  (`@apollo/server`) as the changed component. Correctly found **zero**
  route/middleware relationship for internal plugin-implementation
  files (honestly disclosed).
- **The same root-vs-nested asymmetry as Cases 2/3, but caught this
  time — incidentally:** `packages/server/package.json` also has no
  `test` script of its own. But this commit's diff happens to also
  touch a root-owned file (a Changesets metadata file,
  `.changeset/strong-bears-fly.md`), which made the repository root
  itself (`apollo-server-monorepo`) a second selected component — and
  the root **does** have a real `test` script. This is the mechanism by
  which the gap in Cases 2/3 is sometimes avoided: **only when the diff
  happens to also touch a file the ancestor component owns.** A typical
  source-only PR (like Cases 2 and 3, and like this repository's own
  `uuid` source-file edits) would not trigger it.
- **Validation result:** `npm test` in `apollo-server-monorepo`
  **PASSED** (exit 0) — a real, full, successful run: `pretest` auto-ran
  `npm run compile` (precompile → `tsc --build` → postcompile, wired
  via npm's own lifecycle hook, unlike Case 1), then `jest --verbose`:
  **33 test suites, 570/594 tests passed (24 skipped), 122/122
  snapshots passed**, in 117.953s. **Decision:
  REQUIRE_ADDITIONAL_VALIDATION** (structurally the best available
  outcome under the current, deliberately-conservative policy — see
  `PROJECT_STATE.md` §2).
- **Ground truth:** this repository's real CI is CircleCI, not GitHub
  Actions — the only candidate in this round using a different CI
  system entirely, surfaced to GitHub only as external commit-status
  contexts. All 15 real status contexts for the merge commit are
  `success`, including a genuine Node-version matrix (`ci/circleci:
  NodeJS 20`, `22`, `24`), `Codegen check`, and `Smoke test built
  package`.
- **Classification: correct.** Of the five cases, this is the one
  clean match end-to-end: the analyzer found real validation, ran it
  for real, it genuinely passed, and that outcome matches the real
  repository's own real (and structurally different) CI system.

## Cross-cutting findings

- **The dominant, converging finding of this round: validation
  discovery has no fallback from a changed component to an ancestor
  component's test script.** Three of five repositories (`vite`,
  `superset`, and — absent the incidental changeset-file exception —
  `apollo-server`) have real, active projects where the specific
  package a change lands in owns no test script of its own, and all
  real testing is defined at a workspace root or repository root
  instead. This is a materially different, and apparently common, real
  convention from the per-component-`npm test` shape every prior
  investigation and pilot round (including this milestone's own Case 1
  and Case 4) was built and verified against. Unlike install-path
  resolution (which already walks up to a workspace root via
  `find_workspace_root()`), validation-command discovery has no
  equivalent upward search — it looks only at the exact changed
  component's own `package.json`.
- **A second, narrower finding: at least one real repository's
  validation genuinely requires an explicit build/compile step this
  analyzer's install-then-test model does not run**, when that step is
  not wired into an npm lifecycle hook (Case 1). Case 5 shows the
  identical shape of problem absent when the repository *does* wire it
  through `pretest`. This is a real, reproducible, but seemingly
  narrower and rarer pattern than the validation-discovery gap above —
  observed once here (Case 1), with Case 5 as a real, positive
  contrast rather than a second confirmed instance.
- **Two of five cases (Case 1, Case 4) show real local/CI execution
  divergence traced to environmental causes, not analyzer defects,**
  and in both cases the tool's disclosed behavior — never
  auto-classify a `FAILED`'s cause, always escalate on it — held
  exactly as designed. Case 4's divergence is independently corroborated
  by the target repository's *own* real CI re-run also showing
  flakiness (on a different test), which is about as strong as
  evidence for "pre-existing target-repo flakiness, not this tool's
  fault" gets without repo maintainer input.
- **Component and route discovery generalized correctly across every
  structural variation tested:** a 40+-package npm workspace three
  levels deeper than any repository used to build the feature (Case
  1); a real pnpm-only monorepo where the disclosed non-support
  boundary had to hold on its own, not just in unit tests (Case 2); a
  genuinely polyglot, 10,000+-file repository where the real JS
  component sat three directories deep and a simultaneously-changed
  Python file had to be correctly ignored rather than guessed at (Case
  3); a single-package non-workspace repository (Case 4); a small
  monorepo with real internal package interdependencies (Case 5). No
  case produced a fabricated component, a fabricated route, or a
  fabricated relationship.
- **Workspace-aware install (0.12.0-pilot) generalized correctly** to a
  materially larger and deeper real monorepo than it was built or
  verified against (Case 1: `install ran at workspace root: .` fired
  correctly on a 40+-package tree), and correctly declined to fire on
  a real pnpm-only monorepo it was never designed to support (Case 2).
- **The unauthenticated GitHub API rate limit is a real, binding
  constraint under realistic multi-repository use**, exhausted by this
  round's own research activity alone, independent of anything the
  analyzer itself did. Every `HISTORICAL EVIDENCE (CI)` section in
  every one of this round's five generated reports reads `UNKNOWN /
  insufficient evidence (HTTPError: HTTP Error 403: rate limit
  exceeded)` as a direct result — correctly and distinctly labeled as
  rate-limited rather than silently treated as "no CI history exists,"
  consistent with the product's existing disclosed behavior, but a
  concrete illustration of how quickly that state is reached in
  practice.

## Classification summary

| # | Repository | Analyzer decision | Real CI outcome | Classification |
|---|---|---|---|---|
| 1 | opentelemetry-js | ESCALATE (2 FAILED) | 44/44 checks passed | Environmental limitation (missing non-lifecycle build step) — not a confirmed analyzer defect |
| 2 | vite | ESCALATE (no validation available) | Root-level suite passed | **False negative** — real coverage gap, no ancestor test-script fallback |
| 3 | superset | ESCALATE (no validation available) | Frontend Build CI passed | **False negative** — same gap as #2, independently reproduced |
| 4 | undici | ESCALATE (1 FAILED, unrelated test) | 36/38 at merge; later re-run shows real, different flakiness | Environmental limitation (pre-existing target-repo flakiness, independently corroborated) — not an analyzer defect |
| 5 | apollo-server | REQUIRE_ADDITIONAL_VALIDATION (real PASS) | CircleCI, 15/15 contexts success | **Correct** |

No INCONCLUSIVE (timeout/infrastructure) outcomes occurred in this
round — every selected validation either ran to a real, definite
result or was honestly reported as unavailable.

## User-impact assessment

In all five cases, a pilot user would have received truthful,
non-fabricated evidence — the tool never claimed more than the
evidence supported, and it never silently treated "I didn't find a
test script" as "there is no relevant test." But two of five cases
(40%) would leave a real user with a materially incomplete picture:
told "no validation available, escalate," when real, meaningful,
passing CI validation for their exact change existed one directory
away. That is a bigger practical cost than an environmental
false-`FAILED` (Cases 1, 4) — a user re-running a `FAILED` locally has
a natural next step (check CI, re-run, ask a maintainer); a user told
"no validation exists" for a change in a real monorepo with real root-
level tests has less reason to go looking further, and may reasonably
conclude their change is genuinely untested when it is not.

## Overall verdict

**READY WITH KNOWN LIMITATIONS — generalization mostly holds; one
real, converging gap found.**

Component/route discovery, the pnpm non-support boundary, and the
0.12.0-pilot workspace-install redirect all generalized correctly
across five structurally unrelated real repositories, including ones
substantially larger and more complex than anything previously used to
build or verify these mechanisms. Nothing was fabricated in any case,
across risk assessment, impact discovery, or validation reporting.

This round is not an unconditional `READY`, because it surfaced one
concrete, reproducible, and — critically — **repeated** limitation:

1. **Validation-command discovery has no fallback from a changed
   component to an ancestor (workspace-root or repository-root) test
   script**, unlike install-path resolution, which already does walk
   up to a workspace root. Observed independently in 2 of 5 real
   repositories (`vite`, `superset`), with a third (`apollo-server`)
   showing the same underlying gap only narrowly avoided by
   incidental luck in the specific diff shape. This is the primary,
   actionable finding of this milestone.

A second, narrower observation — at least one real repository's
validation genuinely needs a non-lifecycle-hooked build/compile step
this analyzer's install-then-test model doesn't run (Case 1) — is
reported with lower confidence: it is real and reproducible, but
observed once, with a real positive counter-example (Case 5) showing
the same class of problem does not occur when a repository wires
compile into `pretest`. It may be worth folding into the same future
investigation as finding 1, or treated separately; that is a judgment
call for whoever reviews this evidence next, not a decision this
report makes.

Per this milestone's explicit fix policy, none of the above has been
implemented or even scoped into a fix here — this document is evidence
only, per the instruction to wait for an explicit decision before
starting further work.

## Recommended next action

Scope a narrow, evidence-driven investigation into ancestor-fallback
validation-command discovery (finding 1 above) — the single
best-evidenced, most consistently-reproduced, and highest-user-impact
gap this round found. Whether the narrower build-step finding (Case 1)
should be folded into that same investigation or handled separately is
a call for whoever authorizes that next step, not something this
report resolves.

---

## Completion gate

- [x] Baseline `main` unchanged (`e37bc30`; this branch adds only this
  report and its supporting selection-records document).
- [x] No `.py` source changes.
- [x] No policy/risk/recommendation changes.
- [x] No `.github/workflows/` changes.
- [x] No new repository-specific behavior.
- [x] Existing tests pass — 135/135, confirmed before and after this
  round.
- [x] All 5 candidates are real, fresh (not used in any prior
  investigation or pilot round in this project), and reproducible
  (exact commit SHAs recorded above and in the selection records).
- [x] Raw evidence preserved — quoted directly from the actual
  generated reports and from the real repositories' own CI systems
  throughout this document.
- [x] Generated artifacts (reports, `node_modules`, cloned
  repositories) remain uncommitted — produced under a scratch
  directory outside this repository.
- [x] This report and its selection records are committed under
  `pilot/reports/` and `docs/decisions/` respectively.
- [x] None of the seven previously-deferred §4 items were reopened;
  where this round's evidence touches one (the CI rate-limit
  constraint, and the FAILED-classification question), it is noted
  as corroborating evidence for that existing deferred item, not
  reopened here.
- [x] No implementation PR opened as part of this milestone.
