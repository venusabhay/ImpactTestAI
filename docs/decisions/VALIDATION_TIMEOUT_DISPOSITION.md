# Validation timeout (Option A): implementation review + disposition

**Status: implemented, not committed.** Sitting on branch
`feature/validation-timeout-proposal`'s working tree, awaiting approval
before commit. Nothing described here has been pushed or merged.

## 1. Files changed in ImpactTestAI

| File | Change |
| --- | --- |
| `slice/analyze_change.py` | `run_validation()` gains a `validation_timeout_seconds=180` parameter, used in place of the previous hardcoded `timeout=180` literal; each outcome dict gains a `timeout_seconds` field; `main()` gains a `--validation-timeout-seconds` CLI flag (default `180`) and passes it through; `report.md`'s `VALIDATION RESULT` section gains a `timeout allowed: {n}s` line per outcome; `TOOL_VERSION` bumped to `0.8.0-pilot` with an inline changelog entry. 31 lines changed. |
| `slice/tests/test_analyze_change.py` | 6 new tests (122 lines): default-timeout verification, explicit-timeout passthrough, `timeout_seconds` recorded on both a timed-out and a completed outcome, the pre-existing timeout→`ESCALATE` contract test (updated, not weakened), and one integration-level test using a real (unmocked) subprocess proving a too-short timeout fails while an explicit extension on the identical command succeeds. |

Also present in the working tree, unrelated to this task and not part of
this change: `REPOSITORY_HYGIENE_AUDIT.md`, `slice/VALIDATION_TIMEOUT_PROPOSAL.md`
(the proposal this implements). Nothing else.

`design8.md`, `design9.md`, `discovery.py`, `build_risk_assessment()`,
`final_recommendation()`, and `build_validation_decision()` — **zero
lines changed** (confirmed by `git diff --stat`, which lists only the two
files above).

## 2. Exact behavioral change

One literal became one parameter. Before:

```python
result = subprocess.run(v["command"], cwd=svc_dir, shell=True, capture_output=True, text=True, timeout=180, env=env)
```

After:

```python
result = subprocess.run(v["command"], cwd=svc_dir, shell=True, capture_output=True, text=True,
                         timeout=validation_timeout_seconds, env=env)
```

`validation_timeout_seconds` defaults to `180` in `run_validation()`'s
signature and is set from the new `--validation-timeout-seconds` CLI flag
(also defaulting to `180`) in `main()`. No other line in the
timeout-handling code path changed.

## 3. Confirmation: default remains 180s

Confirmed by inspection (the parameter's default value, and the flag's
`default=180`) and by test: `test_run_validation_default_timeout_is_180_seconds`
asserts `subprocess.run` is called with `timeout == 180` when no override
is supplied.

## 4. Confirmation: timeout → `INCONCLUSIVE` → `ESCALATE` semantics unchanged

The `except subprocess.TimeoutExpired` handler, the `INCONCLUSIVE` result
value, the `INFRASTRUCTURE (timeout)` classification, and
`final_recommendation()`'s `any_inconclusive or no_validation_ran →
ESCALATE` branch are all byte-for-byte unchanged. Confirmed by:

- `test_run_validation_reports_inconclusive_on_timeout` — a timeout still
  produces `INCONCLUSIVE`, never `PASSED`/`FAILED`.
- `test_timeout_outcome_never_reaches_accept_or_require_additional_validation`
  — an `INCONCLUSIVE`/timeout outcome still forces `ESCALATE` across every
  risk-level × confidence combination.
- The real Archify comparison (§7): the 180s run produced `INCONCLUSIVE`
  → `ESCALATE`; nothing about this change altered that outcome for a
  command that genuinely doesn't finish in time.

## 5. Confirmation: `timeout_seconds` present in both report and audit output

Verified directly against real output (not just unit tests), using a
synthetic `sleep 1 && exit 0` fixture:

- `report.md`: `- timeout allowed: 10s` line appears under both a
  `PASSED` outcome (10s timeout) and an `INCONCLUSIVE` outcome (3s
  timeout, real npm startup overhead pushed the command past it).
- `audit.json`: `outcomes[0]["timeout_seconds"]` present with the correct
  value in both cases (verified: `3`, `10`, and — in the Archify runs
  below — `600`).

## 6. ImpactTestAI test result

**95/95 passing** (`python3 -m pytest slice/tests/`) — 92 baseline + 3 net
new after accounting for one renamed test. This is the ImpactTestAI
implementation's own test suite, independent of anything Archify's suite
does.

## 7. Archify comparison: 180s vs. 600s

| | 180s (default, original run) | 600s (explicit) |
| --- | --- | --- |
| Result | `INCONCLUSIVE` (`INFRASTRUCTURE (timeout)`) | `FAILED` (exit code 1) |
| Duration | timed out at 180s | 411s — completed, did not time out |
| Tests | not run to completion | 722 passed, 1 failed, 25 skipped |
| Decision | `ESCALATE` ("validation could not be completed") | `ESCALATE` ("at least one selected validation failed") |
| Risk level | LOW (unchanged) | LOW (unchanged) |

The mechanism did exactly what it was built to do: raising the timeout
did not change *how* a result gets judged, only *whether validation got
far enough to produce a real result at all*. In this case that real
result was a failure, not a pass — reported as such, not smoothed over.

## 8. The failing Archify test, and why it is believed unrelated

**Test:** `cli: deliver --open launches only the committed absolute artifact as one argument`
(`test/cli.test.mjs:284`). It asserts a CLI-launched file reports
`status: 'opened'`; observed `status: 'failed'` for a deliberately
adversarial target path containing Unicode, a quote, and spaces
(`.../-复杂 path 'quoted'/verified diagram.html`), i.e. it exercises the
CLI's `--open` flag invoking the OS `open` command.

**Basis for "believed unrelated," not "confirmed unrelated":**

- The reviewed diff (`codex/fix-site-language-continuity`) touches only
  `docs/*.html`, template files, and `docs/assets/site-language.js`, plus
  two *other* test files (`readme-showcase.test.mjs`,
  `site-language-continuity.test.mjs`). `test/cli.test.mjs` is not in the
  changeset.
- The same commit's suite was run three times total in this
  investigation: once cleanly (723 passed, 0 failed, an earlier informal
  run) and twice with this identical single failure (722/1/25 both
  times) — the same test, the same assertion, each time it failed. That
  pattern (intermittent, always the same assertion, on a test that
  shells out to an OS-level `open` command against an adversarial path)
  is consistent with environment-dependent flakiness in this sandboxed
  execution environment (no interactive GUI session) rather than a
  deterministic defect.
- This is a **belief supported by circumstantial evidence** (unrelated
  file scope, inconsistent reproduction, an OS-integration point known to
  be timing/environment sensitive) — not a proven root cause. No code in
  `cli.test.mjs` or the `open`-invocation path was read or debugged as
  part of this investigation.

## 9. Explicit disposition

| Question | Answer |
| --- | --- |
| ImpactTestAI implementation (this change) | **PASS** — 95/95 tests, default unchanged, timeout→`INCONCLUSIVE`→`ESCALATE` chain unchanged, `timeout_seconds` recorded in both outputs, verified against real (not just mocked) execution. |
| Archify validation (the target repository, this PR) | **FAIL / `ESCALATE`** — `npm test` exited 1. This is what the analyzer observed and is what it reported; it is not being relabeled. |
| Failure attribution to the PR under review | **UNKNOWN / insufficient evidence** — the failing test is outside the diff's scope and reproduced inconsistently (1 pass, 2 fails across 3 runs of the identical commit), but no debugging was done inside Archify to confirm a root cause. This is circumstantial, not proven. |

Per instruction: no changes were made to Archify, no flake suppression or
retry logic was added anywhere, the analyzer's failure semantics were not
touched, and nothing has been committed. Awaiting review.
