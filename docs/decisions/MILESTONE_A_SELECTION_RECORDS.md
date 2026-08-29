# Milestone A — Repository Selection Records

Baseline: ImpactTestAI `main` @ `e37bc30`, `TOOL_VERSION=0.12.0-pilot`, `POLICY_VERSION=repo-plus-ci-plus-cross-service-plus-discovery-v9`, 135/135 tests passing. No code changes made before or during selection.

All candidates verified against real, live repository state (package.json/workspace files fetched directly from GitHub; commit/PR/CI evidence fetched via GitHub REST API and, once the unauthenticated API rate limit was exhausted, cross-checked via the public GitHub web UI) — not from memory.

---

## 1. open-telemetry/opentelemetry-js

- **Repository:** `open-telemetry/opentelemetry-js`
- **Primary ecosystem:** JavaScript/TypeScript (Node.js + browser)
- **Package manager:** npm workspaces — root `package.json` `"workspaces"` is a real plain-array list (`["api", "packages/*", "semantic-conventions", "e2e-tests", "experimental/packages/*", ...]`), no `packageManager` field (plain npm).
- **Repository structure:** Large multi-package monorepo — dozens of independently-versioned instrumentation/SDK packages under `packages/*` and `experimental/packages/*`.
- **CI characteristics:** GitHub Actions, many parallel jobs per commit (44 check-runs observed on the candidate commit): `node-tests` matrix across Node 18/18.19/20/20.6/22/24/26, `browser-tests`, `webworker-tests`, `e2e-tests` matrix, `benchmark-tests`, `lint`, `peer-api-check`, CodeQL, OSSF Scorecard.
- **Candidate historical change:** `61126358cb` — `fix(sdk-metrics): ignore infinity in exponential histograms (#7015)`, parent `26eac901c0`. Touches `packages/sdk-metrics/src/aggregator/ExponentialHistogram.ts` and its test file. All 44 check-runs completed successfully.
- **Why this repository is representative:** A real, large, actively-maintained npm-workspaces monorepo with a genuinely deep package tree (five workspace glob patterns, not just `packages/*`) — the same package-manager convention (`"workspaces"` field) the 0.12.0-pilot milestone was built and unit-tested against, but on a repository with materially more packages and directory depth than the two-repo real-world verification (`socketio/socket.io`, `hagopj13/node-express-boilerplate`) used during that milestone's own development.
- **What analyzer behavior it will test:** Whether `find_workspace_root()` and workspace-aware installation generalize correctly to a much larger, deeper real workspace tree than what the milestone was verified against; whether component/route discovery holds up on an SDK-shaped package (no HTTP routes — a good test of graceful "no route evidence" behavior on a non-server package).
- **Available independent evidence:** GitHub Actions check-runs (44, all `success`) on the exact commit, via `api.github.com/repos/.../commits/{sha}/check-runs` (captured before the unauthenticated API rate limit was exhausted).

---

## 2. vitejs/vite

- **Repository:** `vitejs/vite`
- **Primary ecosystem:** JavaScript/TypeScript
- **Package manager:** **pnpm** — `packageManager: "pnpm@10.34.5"` in root `package.json`, real `pnpm-workspace.yaml` (`packages: ['packages/*', 'playground/**', ...]`). No `"workspaces"` field in `package.json` at all — pnpm's workspace membership lives in a structurally different file this tool's design doc explicitly documents as **out of scope** (`WORKSPACE_AWARE_INSTALL_DESIGN.md` §2: "pnpm is explicitly not supported").
- **Repository structure:** Large monorepo (`packages/vite` is the core package, plus `playground/**` fixtures used only for internal testing).
- **CI characteristics:** GitHub Actions; the candidate PR shows "20 of 21 checks passed."
- **Candidate historical change:** `ee644014aa` — `chore: delete unused PluginContainerOptions (#23382)`, parent `493cc7d432`. Single-file change to `packages/vite/src/node/server/pluginContainer.ts` (removes an unused exported type). PR #23382 merged, 20/21 checks passed.
- **Why this repository is representative:** The single best available real-world negative control for the workspace-install milestone's own disclosed scope boundary — a real, active, pnpm-only repository with no npm/Yarn `"workspaces"` field anywhere.
- **What analyzer behavior it will test:** Whether `find_workspace_root()` correctly returns `None` (byte-for-byte prior, non-workspace-redirect behavior) on a repository that *is* a real workspace monorepo but through a manager this milestone deliberately does not read — i.e., does the disclosed pnpm boundary hold on a real repository, or does something in `_workspace_patterns()`/ancestor-walking misfire on pnpm's differently-shaped `package.json`. Secondarily, a low-blast-radius single-file removal is a good false-positive check (does the analyzer avoid over-reporting impact for a genuinely unused, unexported symbol).
- **Available independent evidence:** PR #23382's checks summary ("20 of 21 checks passed"), read from the public PR page after the REST API rate limit was hit.

---

## 3. apache/superset

- **Repository:** `apache/superset`
- **Primary ecosystem:** Polyglot — Python (Flask backend) + TypeScript/React (`superset-frontend/`, a real npm/Yarn-workspace-shaped sub-project: `"workspaces": ["packages/*", "plugins/*", "src/setup/*"]`).
- **Package manager:** pip/setuptools for the Python side; npm workspaces for `superset-frontend/`.
- **Repository structure:** Large polyglot monorepo — Python application code at the root, a nested JS/TS workspace monorepo under `superset-frontend/`.
- **CI characteristics:** Extensive GitHub Actions surface — the candidate PR shows 80 checks, including path-filtered/component-specific jobs (`Frontend Build CI (unit tests, linting & sanity checks)`, `Python-Unit`, `Python-Integration`, `E2E`, `Playwright Experimental Tests`, `Python Presto/Hive`, `CodeQL`, `Codecov`).
- **Candidate historical change:** `de33efae98` — `fix(table-chart): support where for adhoc columns with server-side pagination (#42706)`, parent `b30d569028`. Genuinely polyglot: touches `superset-frontend/plugins/plugin-chart-table/src/TableChart.tsx` (JS/TS) **and** `superset/models/helpers.py` (Python), plus a Python unit test file. PR #42706 merged.
- **Why this repository is representative:** A real repository that is simultaneously polyglot at the top level and an npm workspace one level down — this is the sharpest available test of the product's disclosed "Node.js/Express-style-convention specific" boundary (`PRODUCT_VALIDATION_SPEC.md` §2) inside a single real, mixed-language change, rather than inferring the boundary from a pure-Python repo where the tool would trivially find nothing.
- **What analyzer behavior it will test:** Whether component discovery correctly locates the real JS component (`superset-frontend/plugins/plugin-chart-table`) nested three directories deep inside a much larger polyglot tree, correctly ties the changed `TableChart.tsx` to it, and — just as importantly — says nothing false about the simultaneously-changed Python file rather than fabricating JS-shaped findings for it.
- **Available independent evidence:** PR #42706's checks tab (80 named jobs, read from the public PR page), including a component-specific frontend job (`Frontend Build CI`) directly comparable to whatever validation the analyzer selects for the JS component.

---

## 4. nodejs/undici

- **Repository:** `nodejs/undici`
- **Primary ecosystem:** JavaScript (Node.js), Node.js core team-maintained HTTP client.
- **Package manager:** Plain npm, **single package** — no `"workspaces"` field, no monorepo structure at all.
- **Repository structure:** Single-package repository — the deliberate structural opposite of candidates #1/#2/#3/#5, which are all monorepos of one kind or another.
- **CI characteristics:** GitHub Actions with a genuine `strategy: matrix` (`node-version` × `runs-on` in `ci.yml`'s `test` job), a separate conditional `dependency-review` job (`if: github.event_name == 'pull_request'`), plus `lint`, `autobahn`, `bench`, `codeql`, `scorecard`, and Node.js-nightly workflows — a materially more matrix/condition-heavy CI architecture than any workspace candidate above.
- **Candidate historical change:** `fc3450dcf1` — `fix(socks5-proxy-agent): destroy socket when negotiation times out (#5709)`, parent `efc4f09f4a`. Real bug fix (a socket leak on SOCKS5 negotiation timeout) in `lib/dispatcher/socks5-proxy-agent.js`, with a real regression test added in `test/socks5-proxy-agent.js`. PR #5709 merged, "36 of 38 checks passed."
- **Why this repository is representative:** Tests the analyzer against a real, non-monorepo Node.js repository with a CI architecture built around a genuine version/OS matrix rather than a package-per-workspace fan-out — the single clearest test of "CI architecture" diversity in this selection, and the only candidate with zero workspace-detection surface at all (a true `find_workspace_root() -> None` case on a repository that was never a workspace to begin with, as opposed to vite's "is a workspace, but the wrong kind").
- **What analyzer behavior it will test:** Baseline non-workspace behavior generalization on a real, unrelated repository (not the small fixture/pilot repos used during 0.12.0-pilot's own development); whether a real bug-fix-plus-regression-test change is correctly identified and whether the analyzer's validation selection lines up with what the PR's own real matrix actually ran and passed.
- **Available independent evidence:** PR #5709's checks tab and merge summary ("36 of 38 checks passed"), read from the public PR page.

---

## 5. apollographql/apollo-server

- **Repository:** `apollographql/apollo-server`
- **Primary ecosystem:** JavaScript/TypeScript (GraphQL server).
- **Package manager:** npm workspaces (`"workspaces": ["packages/*"]`), no `packageManager` field.
- **Repository structure:** Monorepo with a small number of packages with real internal dependency relationships: `server` (the core, `@apollo/server`), `gateway-interface`, `plugin-response-cache`, `integration-testsuite`, `usage-reporting-protobuf`, `cache-control-types` — several of these exist specifically to test or extend `server`, i.e. real indirect/internal consumers within the same repository.
- **CI characteristics:** **CircleCI**, not GitHub Actions — the only candidate using a different CI system entirely, surfaced to GitHub only as external commit statuses (`ci/circleci: <job>`), not native check-runs. Verified 15 real status contexts on a recent commit, including a genuine Node-version matrix (`ci/circleci: NodeJS 20/22/24`), `Codegen check`, `Smoke test built package`, `Full incremental delivery tests with graphql 17 alpha 9`, `codecov/project`, `codecov/patch`.
- **Candidate historical change:** `3f46c51d0f` — `fix(deps): remove vulnerable dependency uuid (#8201)`, parent `150adc2`. Real dependency-removal fix confined to `packages/server` (replaces the `uuid` package with `crypto.randomUUID()` in two internal source files, drops `uuid` from `packages/server/package.json`). PR #8201 merged; CircleCI commit status `success` across all 15 contexts (captured via the REST API before the rate limit was exhausted).
- **Why this repository is representative:** The only candidate whose CI evidence has to be gathered through an entirely different mechanism (external CircleCI status contexts rather than GitHub Actions check-runs) — deliberately exercises the "Available independent evidence" comparison itself, not just the analyzer. Its package topology is the sharpest real example of "shared libraries, indirect consumers" among the five: `plugin-response-cache` and `integration-testsuite` genuinely depend on `server`'s exported surface within the same workspace.
- **What analyzer behavior it will test:** Whether the analyzer's impact discovery recognizes that a change confined to `packages/server`'s internals (no exported-API change here) correctly does **not** over-report impact on `plugin-response-cache`/`integration-testsuite`/`gateway-interface` (a false-positive check on indirect-impact reasoning) — the intentional counterpart to candidates that test whether real cross-package impact is found when it exists.
- **Available independent evidence:** GitHub's mirrored CircleCI commit-status contexts for the merge commit (15 contexts, all `success`), captured via the REST API `commits/{sha}/status` endpoint.

---

## Diversity summary

| Axis | 1. otel-js | 2. vite | 3. superset | 4. undici | 5. apollo-server |
|---|---|---|---|---|---|
| Ecosystem | JS/TS | JS/TS | Python + JS/TS | JS | JS/TS |
| Package manager | npm workspaces | **pnpm** | npm workspaces (nested) | plain npm, no workspace | npm workspaces |
| Structure | large monorepo | large monorepo | polyglot monorepo | **single package** | small monorepo |
| Dependency topology | many independent packages | plugin/bundler core + playgrounds | backend/frontend split | none (single package) | core + indirect internal consumers |
| CI architecture | GH Actions, version/env matrix | GH Actions | GH Actions, path-filtered per-component | GH Actions, version×OS matrix | **CircleCI** (external status) |
| Test organization | mocha-family, per-package | vitest-family | **Jest** (frontend) + pytest (backend) | custom Node test runner | Jest |

No two candidates share the same package manager + repository structure + CI architecture combination.
