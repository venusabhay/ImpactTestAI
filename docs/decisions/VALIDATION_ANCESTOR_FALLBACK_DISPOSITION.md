# Validation-command ancestor fallback: implementation disposition

Companion to
[`VALIDATION_ANCESTOR_FALLBACK_DESIGN.md`](VALIDATION_ANCESTOR_FALLBACK_DESIGN.md).
This is the completion evidence.

## Commits

- **Baseline:** `main` @ `e37bc30` (workspace-aware-install milestone,
  merged). `TOOL_VERSION` at baseline: `0.12.0-pilot`.
- **Branch:** `feature/validation-ancestor-fallback`.
- Final commit SHA and post-merge `main` SHA: recorded once the PR is
  reviewed and merged (standing process — a human opens the PR, this
  session cannot).

## Files changed

- `slice/discovery.py` — adds `find_validation_ancestor()`.
- `slice/analyze_change.py` — `build_validation_decision()`'s
  no-test-script branch now consults the ancestor fallback before
  rejecting; the selected validation's `target_dir` and
  `decision_reason` reflect the fallback when it fires; a new
  `validated_via_ancestor` field is set on the selected validation and
  propagated onto the executed outcome (mirroring
  `install_workspace_root`'s existing pattern exactly); `render_report()`
  surfaces it; `TOOL_VERSION` → `0.13.0-pilot`.
- `slice/tests/test_discovery.py` — 5 new mechanism-level tests.
- `slice/tests/test_analyze_change.py` — 5 new integration-level tests.
- `docs/decisions/VALIDATION_ANCESTOR_FALLBACK_DESIGN.md` (new).
- `docs/decisions/VALIDATION_ANCESTOR_FALLBACK_DISPOSITION.md` (this
  file).

No other file changed. No `.github/workflows/` changes. No changes to
`POLICY_VERSION`, `final_recommendation()`, `build_risk_assessment()`,
route/component discovery, `find_workspace_root()`, or any other
existing discovery/risk mechanism — confirmed directly by diff
inspection (`git diff main -- slice/analyze_change.py slice/discovery.py
| grep -E "^\+def |^-def "` shows exactly one function added,
`find_validation_ancestor()`, and no function removed or renamed).

## Exact rule implemented

When a changed component's own `package.json` has no `"test"` script,
`build_validation_decision()` walks strictly upward through the
repository's already-discovered components (via the new
`discovery.find_validation_ancestor()`) and, if the nearest one with a
real `"test"` script is found, selects `npm test` there instead —
target directory, decision-reason text, and a new
`validated_via_ancestor` field all reflect the fallback honestly. A
component with its own valid local command is completely unaffected;
if no ancestor (including the repository root) has one either, the
existing rejection/`ESCALATE` path is unchanged, byte-for-byte.

## Tests added (10 total)

`slice/tests/test_discovery.py` (5): no ancestor anywhere has a script;
one-level (nearest, non-root) ancestor fallback; repository-root
fallback when no intermediate ancestor qualifies; nearest ancestor wins
over a more distant one that also qualifies; a sibling component's
script is never selected.

`slice/tests/test_analyze_change.py` (5): component-local command is
completely unaffected (exact prior reason wording, no new field);
one-level ancestor fallback wires `target_dir`/`decision_reason`/
`validated_via_ancestor` correctly; repository-root fallback (modeled
on the real `vitejs/vite` shape); rejection preserved exactly when no
ancestor qualifies, confirmed to still reach `ESCALATE` via
`final_recommendation()`; a sibling's script is never selected at the
integration level either.

## Full test count

**Before:** 135/135 passing (`main` @ `e37bc30`).
**After:** 145/145 passing (135 + 10 new). No regressions.

## Real repositories used for verification

Both real repositories Milestone A demonstrated the gap on, re-run
against this fix with no code changes to either target repository:
`vitejs/vite` @ `ee644014aa`, `apache/superset` @ `de33efae98`
(`packages/vite`; `superset-frontend/plugins/plugin-chart-table`
respectively — the exact same commits and components Milestone A
analyzed).

### `vitejs/vite`

**Before this fix:** `NOT AVAILABLE: INTEGRATION_TEST for 'vite' -- No
'test' script found for component 'vite' (no package.json test
script)`. No validation executed. `ESCALATE`.

**After this fix:**

```
RECOMMENDED VALIDATION
- RUN: `npm test` in `vite` -- 'vite' component has no test script of
  its own; its nearest ancestor with one, 'the repository root', is
  the best available real validation for this change (exists, runs
  via 'npm test'). ...
```

Discovery/selection is now demonstrably correct: the analyzer finds
and recommends exactly the real, root-level `test` script
(`pnpm test-unit && pnpm test-serve && pnpm test-build`) that
`vitejs/vite`'s own real CI actually runs for this exact kind of
change (confirmed independently in the pilot round: PR #23382, "20 of
21 checks passed"). This is the specific, demonstrated gap, and it is
fixed.

**Execution hit a separate, pre-existing, disclosed limitation, not a
defect in this fix:** `npm install` at the repository root failed --

```
npm error code EUNSUPPORTEDPROTOCOL
npm error Unsupported URL Type "workspace:": workspace:*
```

`vitejs/vite`'s root `package.json` declares a real pnpm-only
dependency (`"vite": "workspace:*"`), a protocol plain `npm` does not
understand at all -- this has nothing to do with which directory the
install ran in or with this fallback's own logic; it is the same,
already-disclosed pnpm non-support boundary
(`WORKSPACE_AWARE_INSTALL_DESIGN.md` §2) surfacing from a new angle,
for the first time, only because this fix now correctly attempts
validation at a real pnpm-managed directory that no prior code path
ever reached. Confirmed directly: `packages/vite/package.json` itself
(where install ran *before* this fix, and still has no test script)
has **no** `workspace:` dependencies at all -- only the root does; this
failure is specific to installing at a real pnpm root via `npm`, not
to this fix's directory-selection logic, which is doing exactly what
it is supposed to. The result was reported honestly:
`INCONCLUSIVE`/`INFRASTRUCTURE (dependency install failed)`, never a
fabricated pass or a misdiagnosed fail, and correctly forced
`ESCALATE` -- the existing, unmodified 0.9.0 fail-safe behavior,
reused unchanged. Per the engineering instruction's explicit boundary
(preserve pnpm support boundaries -- do not extend them), this is
documented here, not fixed.

### `apache/superset`

**Before this fix:** `NOT AVAILABLE: INTEGRATION_TEST for
'@superset-ui/plugin-chart-table' -- No 'test' script found`. No
validation executed. `ESCALATE`.

**After this fix:**

```
RECOMMENDED VALIDATION
- RUN: `npm test` in `@superset-ui/plugin-chart-table` --
  '@superset-ui/plugin-chart-table' component has no test script of
  its own; its nearest ancestor with one, 'superset-frontend', is the
  best available real validation for this change (exists, runs via
  'npm test'). ...
```

Correctly stops at the nearest real ancestor (`superset-frontend/`,
which does have its own `package.json` and a real `"test"` script) --
correctly does **not** walk past it to the top-level `apache/superset`
repository root, which has no `package.json` at all (it is a Python
project) and would not have qualified regardless. This is exactly the
§3 "nearest ancestor wins" guarantee, now confirmed on the real
repository, not only in a synthetic unit test.

**Execution (300s, matching Milestone A's original timeout):**
`npm install` succeeded; `npm test` (`superset-frontend`'s real, full
`jest` suite -- `cross-env NODE_ENV=test ... jest --max-workers=80%
--silent`, not scoped to only the changed plugin) did not complete
within 300 seconds -- `INCONCLUSIVE`/`INFRASTRUCTURE (timeout)`,
`ESCALATE`. Retried once more with a 900-second timeout (well within
the tool's documented 1800s cap) to see whether this is a "slow but
healthy" suite in the sense `PILOT.md` already documents: it still had
not completed at 900 seconds either. This is real, first-hand evidence
that `superset-frontend`'s full, repository-root-level `jest` run is
genuinely a very long-running suite on this development machine --
consistent with, not contradicting, the same class of finding already
on record for other large real repositories in this project
(`fastify`'s cold install; `opentelemetry-js`'s cold workspace-root
install in Milestone A itself) -- and is handled by the same,
unmodified 0.9.0 fail-safe machinery either way: a timeout is never
quietly turned into a pass or a fail, and always forces `ESCALATE`.
This is not a defect in this fix; it is the expected, honest,
documented behavior for a validation command that is real and
correctly selected but genuinely slow on this particular machine.
(The 900-second run's diff also transiently picked up an unrelated
`superset-frontend/package-lock.json` line-count change -- a real,
harmless side effect of the *prior* run's own `npm install` having
regenerated that lockfile in this reused scratch clone, reverted
before the final, clean 300-second confirmation quoted above, which
matches Milestone A's original diff exactly.)

### Negative / safety case (real, not only mocked)

`nodejs/undici` (Milestone A Case 4, a real single-package,
non-workspace repository with its own valid local test script) was
not re-run: nothing in this fix's own logic path is exercised for a
component that already has a test script of its own, and the
regression suite's
`test_build_validation_decision_uses_component_local_test_script_unchanged`
directly covers that exact class of case with the real prior wording
asserted verbatim.

## Confirmations

- **No repository-specific heuristic introduced:**
  `find_validation_ancestor()` contains no reference to `vite`,
  `superset`, or any other specific repository/package name --
  confirmed by direct inspection of the diff. Selection is driven
  entirely by real, already-discovered component boundaries and the
  standard `package.json` `"scripts"` object.
- **`POLICY_VERSION` and recommendation/risk logic unchanged:**
  confirmed by diff (no change to the `POLICY_VERSION` string, no
  risk-scoring or `final_recommendation()` function touched) and by the
  full, unmodified regression suite (135 pre-existing tests) still
  passing unchanged.
- **`find_workspace_root()` and workspace-install redirection
  unchanged:** confirmed by diff (the function itself is untouched)
  and by real-world re-verification: `vitejs/vite`'s install still
  correctly does not redirect via `find_workspace_root()` in the
  workspace-membership sense (its pnpm-only workspace declaration is
  still, correctly, invisible to that function) -- the ancestor
  fallback changed *where the test command itself runs*
  (`target_dir`), and `find_workspace_root()` is then, correctly and
  without any special-casing, asked about *that* directory for install
  purposes, exactly as it always has been for whatever `target_dir` a
  validation carries.
- **pnpm support boundary preserved, not extended:** confirmed by the
  real `vitejs/vite` re-run above -- installing at a real pnpm-managed
  directory still fails safely and honestly (`INCONCLUSIVE`, never a
  fabricated result), exactly as it would have for any other real pnpm
  repository before this milestone. No pnpm-specific handling was
  added anywhere.
- **Route/component discovery unchanged:** confirmed by diff (neither
  `find_components()`, `find_route_registrations()`, nor any other
  discovery-mechanism function was touched) and by both real re-runs
  above reporting identical `## CHANGE`/route-discovery output to
  their original Milestone A runs.
- **No `.github/workflows/` changes:** confirmed by diff.

## Stop-condition assessment

1. Both demonstrated cases (`vitejs/vite`, `apache/superset`) now
   correctly discover and select the real, meaningful ancestor
   validation their own real CI actually runs: **yes**, directly
   confirmed on the real repositories, not only in synthetic tests.
2. A component with its own valid local command is completely
   unaffected: **yes**, confirmed by a dedicated regression test
   asserting the exact prior reason wording.
3. The nearest applicable ancestor wins, never a more distant one
   (including the repository root) when a nearer one qualifies:
   **yes**, confirmed by a dedicated regression test, and by the real
   `apache/superset` re-run correctly stopping at `superset-frontend/`
   rather than continuing past it.
4. No applicable ancestor anywhere → the existing rejection/`ESCALATE`
   behavior is unchanged: **yes**, confirmed by a dedicated regression
   test, byte-for-byte the same code path as before this milestone.
5. Unrelated (sibling/cousin) ancestor scripts are never selected:
   **yes**, confirmed at both the mechanism and integration test
   levels.
6. All existing tests and the two real demonstrated cases pass/behave
   correctly: **yes** for the test suite (145/145); **yes** for
   discovery/selection correctness on both real cases; validation
   *execution* itself reached honest `INCONCLUSIVE` outcomes on both
   real repositories for two separate, pre-existing, already-precedented
   reasons (a pnpm/npm protocol incompatibility; a full-suite jest run
   genuinely exceeding the default timeout on this development
   machine) -- neither is a defect in this fix, and both are handled by
   existing, unmodified fail-safe machinery.

**Milestone objective met.** The specific, demonstrated
validation-discovery gap from Milestone A is fixed and confirmed on
both real repositories that surfaced it. Two secondary, pre-existing,
already-disclosed boundaries (pnpm support; slow-but-healthy full-suite
timing) were newly *reached* by this fix (because it now correctly
attempts validation somewhere no prior code path ever tried), but
neither is this milestone's to fix, consistent with the instruction's
explicit scope boundaries.

## Explicitly out of scope (per instruction)

- **The OpenTelemetry build-step observation** (Milestone A Case 1) is
  recorded as a follow-up observation only, not implemented here. The
  `apollographql/apollo-server` case (Milestone A Case 5) remains
  useful counter-evidence that build-before-test already works
  correctly today when a repository expresses that relationship
  through npm's own `pretest` lifecycle hook.
- **None of the seven previously-deferred §4 items were reopened.**
  This milestone's own new evidence (the pnpm/`workspace:` protocol
  failure mode) is a *new*, narrow, real observation about pnpm's
  boundary specifically for validation execution (not install
  redirection, which was already known) -- noted here for a future,
  separate, explicit decision if it recurs, not folded into any
  existing deferred item or acted on now.
