# Workspace-aware validation installation: implementation disposition

Companion to [`WORKSPACE_AWARE_INSTALL_DESIGN.md`](WORKSPACE_AWARE_INSTALL_DESIGN.md)
(written before implementation). This is the completion evidence.

## Commits

- **Baseline:** `main` @ `ce6222c` (route-label-composition milestone,
  merged). `TOOL_VERSION` at baseline: `0.11.0-pilot`.
- **Branch:** `feature/workspace-aware-install`.
- Final commit SHA and post-merge `main` SHA: recorded once the PR is
  reviewed and merged (see the standing engineering process — a PR must
  be opened by the user, this session cannot open one itself).

## Files changed

- `slice/discovery.py` — adds `find_workspace_root()`,
  `_workspace_patterns()`, `_matches_workspace_pattern()`.
- `slice/analyze_change.py` — `run_validation()`'s `npm install` step
  now installs at the detected workspace root when one exists;
  `render_report()` surfaces `install_workspace_root` when present;
  `TOOL_VERSION` → `0.12.0-pilot` with changelog.
- `slice/tests/test_discovery.py` — 8 new tests.
- `slice/tests/test_analyze_change.py` — 3 new tests.
- `docs/decisions/WORKSPACE_AWARE_INSTALL_DESIGN.md` (new, pre-implementation).
- `docs/decisions/WORKSPACE_AWARE_INSTALL_DISPOSITION.md` (this file).

No other file changed. No `.github/workflows/` changes. No changes to
`POLICY_VERSION`, `final_recommendation()`, `build_risk_assessment()`,
`build_validation_decision()`, route-label composition, or any other
discovery mechanism — confirmed directly by diff inspection (`git diff
main -- slice/analyze_change.py | grep -E "^\+def |^-def "` shows no
function added or removed; only `find_workspace_root()` and its two
small helpers are new, in `discovery.py`).

## Exact installation rule implemented

For each selected validation, if the component's own directory
(`v["target_dir"]`) is a declared member of an npm/Yarn workspace —
determined by walking upward from it to the nearest ancestor
`package.json` that declares a `"workspaces"` field, and confirming the
component's path actually matches one of that field's declared patterns
— `npm install` runs with `cwd` set to that workspace root instead of
the component's own directory. The validation/test command itself is
completely unchanged: still `cwd=svc_dir`, same command, same timeout,
same everything else. When no workspace is detected (the common case),
`install_dir` collapses to exactly `svc_dir` — the same value used
before this milestone, with no new code path exercised.

## Supported workspace/package-manager conventions

npm workspaces and Yarn (classic and berry) workspaces, both via the
shared, standard `"workspaces"` field in an ancestor `package.json`
(plain-array form and Yarn classic's `{"packages": [...]}` object
form). pnpm's separate `pnpm-workspace.yaml` file is explicitly **not**
supported — a disclosed scope boundary (see design doc §2), not a
silent gap.

## Tests added (11 total)

`slice/tests/test_discovery.py` (8): no-workspace-field control case;
exact-member-path detection (matching `socketio/socket.io`'s own real
shape); wildcard-pattern detection; Yarn classic object-form support;
workspace-exists-but-doesn't-declare-this-component (ambiguous case);
wildcard does not cross a path segment; repo-root component has no
ancestor; intermediate non-workspace-declaring `package.json` is
correctly skipped, not mistaken for a boundary.

`slice/tests/test_analyze_change.py` (3): positive case (install
redirected to workspace root, validation command still runs in the
component, `install_workspace_root` recorded); control/negative case
(ordinary repository installs exactly where it always did,
`install_workspace_root` absent); failure case (a genuine
workspace-install failure — modeled on the real reproduction's exit
127 — stays `INCONCLUSIVE`/`INFRASTRUCTURE`, never a fabricated
`FAILED`, and the validation command is never attempted).

## Full test count

**Before:** 124/124 passing (`main` @ `ce6222c`).
**After:** 135/135 passing (124 + 11 new). No regressions.

## Real repository used for positive verification

`socketio/socket.io`, real commit `7c6ef571` ("fix(parser): reject
binary packets with zero attachments"), package
`packages/socket.io-parser` — the exact real repository and commit
identified in `pilot/reports/2026-08-29-product-validation-pilot.md`,
Case 3. Reproduced fresh, before any code changed, to confirm the
starting failure, and again after implementation.

### Exact validation command/result before the fix

```
npm install   (cwd = packages/socket.io-parser)
npm test      (cwd = packages/socket.io-parser)
```

Result: `npm test` → `FAILED`, exit 127 —

```
> socket.io-parser@4.2.6 test
> npm run format:check && ...
> prettier --check --parser typescript '*.js' 'lib/**/*.ts' 'test/**/*.js'
sh: prettier: command not found
```

Decision: `ESCALATE`. Reproduced identically both before this
milestone's implementation began and against the pre-fix code, exit
code and stderr matching the original pilot report exactly.

### Exact validation command/result after the fix

```
npm install   (cwd = <repo root>, the detected workspace root)
npm test      (cwd = packages/socket.io-parser, unchanged)
```

**Cold `node_modules` (first real run):** the workspace-root install
itself timed out at the existing 300-second default —
`INCONCLUSIVE` / `INFRASTRUCTURE (dependency install timed out)` /
`ESCALATE`, with the new `install ran at workspace root: .` line
present on the outcome. This is real, unmodified 0.9.0 fail-safe
behavior, now correctly reached via the workspace-root path — genuine
evidence for the design's §7 question ("what happens when workspace
installation itself fails"), not a flaw: installing an entire
12-package real monorepo from cold genuinely takes more than 300
seconds on this machine, exactly the same class of finding as the
`fastify` case in the product-validation pilot.

**Warm `node_modules` (dependencies pre-installed, isolating the
install-location question from cold-install timing):** `npm install`
completed; `npm test` progressed to and **passed** its `format:check`
step —

```
> prettier --check --parser typescript '*.js' 'lib/**/*.ts' 'test/**/*.js'
Checking formatting...
All matched files use Prettier code style!
```

— definitively confirming the original failure (`prettier: command not
found`) is resolved: `prettier`, hoisted at the workspace root, is now
found. Validation then proceeded into the package's `compile` step
(TypeScript build) and failed there instead —

```
> rimraf ./build && tsc && tsc -p tsconfig.esm.json && ./postcompile.sh
sed: 1: "./build/esm/binary.js": invalid command code .
```

**This is confirmed to be a separate, pre-existing, unrelated defect**,
not a consequence of this milestone: `packages/socket.io-parser/postcompile.sh`
runs `sed -i '/debug(/d' ./build/esm/*.js` — GNU `sed`'s `-i` accepts no
argument for an in-place edit with no backup; BSD/macOS `sed` (this
development machine) requires an explicit (possibly empty) argument
immediately after `-i`, so the same invocation errors out. This is a
real Linux/macOS build-script portability issue in the target
repository's own tooling, unrelated to workspace-install location, and
per instruction is **documented here, not fixed** — no `sed` shim, no
build-script edit, no environment-variable workaround was added.

### Confirmation that the relevant test suite actually executed

Partially, and honestly reported as such: the package's `format:check`
step (which depends on the exact hoisted dependency this milestone
fixes access to) ran for real and passed. The package's actual `mocha`
unit tests (`test:node`, covering `test/parser.js`) did not run on this
development machine, blocked by the separate, documented macOS/`sed`
issue above — not by anything related to workspace-aware installation.
On the repository's own real Linux CI (where `sed -i` behaves as this
script expects), this same fix would be expected to let the full
`test:node` suite run; that could not be independently confirmed from
this development environment without either modifying the target
repository or installing additional tooling, either of which was
judged out of scope for this milestone's narrow objective.

### Negative / safety case (real, not only mocked)

The existing CI fixture (`slice/fixtures/setup_fixture.sh`, a
non-workspace repository) was re-run post-implementation:
`install_workspace_root` did not appear on its outcome, `npm test`
`PASSED`, decision `REQUIRE_ADDITIONAL_VALIDATION` — byte-for-byte
identical to its pre-milestone baseline.

## Confirmations

- **No repository-specific heuristic introduced:** `find_workspace_root()`
  contains no reference to `socketio`, `socket.io`, `socket.io-parser`,
  `prettier`, or any other specific repository/package/dependency name
  — confirmed by direct inspection of the diff. Detection is entirely
  driven by the standard `"workspaces"` package-manager metadata field.
- **`POLICY_VERSION` and recommendation/risk logic unchanged:** confirmed
  by diff (no change to the `POLICY_VERSION` string, no risk-scoring or
  `final_recommendation()` function touched) and by the unchanged
  regression-test outcomes for `test_timeout_outcome_never_reaches_accept_or_require_additional_validation`,
  `test_install_timeout_outcome_still_escalates`, and the full existing
  0.9.0/0.10.0/0.11.0 test suites, all still passing unmodified.
- **Existing fail-safe behavior unchanged:** validation timeout
  handling, npm-install failure/timeout classification, CI-history
  failure handling, and the `INCONCLUSIVE` → `ESCALATE` guarantee are
  all exercised by the same, unmodified code paths this milestone
  reuses (only `cwd` changes) — confirmed by the cold-install-timeout
  real-world reproduction above, which is exactly this pre-existing
  mechanism firing correctly through the new code path.

## Stop-condition assessment

1. The demonstrated workspace-hoisting failure is resolved: **yes**,
   directly confirmed (`prettier` now found and its check passes).
2. Ordinary repositories retain existing behavior: **yes**, confirmed
   both by a real fixture re-run and dedicated regression tests.
3. Installation failures remain safely classified: **yes**, confirmed
   by a real cold-install timeout reaching the correct, unmodified
   `INCONCLUSIVE`/`ESCALATE` path.
4. The implementation remains narrow and metadata-driven: **yes** — one
   package-manager-standard field, no heuristics, no repository-specific
   code, pnpm explicitly out of scope rather than half-supported.
5. All existing tests and the real workspace pilot case pass: **yes**
   for the test suite (135/135); the real pilot case's core claim
   (dependency availability) is directly confirmed, with one separate,
   unrelated, explicitly-documented environment defect (not this
   milestone's to fix) preventing a full clean end-to-end test-suite
   pass on this particular development machine.

**Milestone objective met.** The one incomplete item (full `mocha`
suite execution on this machine) is blocked by a documented, unrelated,
pre-existing target-repository portability defect, not by anything
this milestone was responsible for — consistent with the instruction to
document rather than fix defects encountered outside this milestone's
scope.
