# Validation timeout: proposal (not implemented)

**Status: proposal only.** No change has been made to `analyze_change.py`'s
behavior. This document exists to establish what timeout policy the pilot
actually wants before touching the code — see the Archify diagnostic below
for why this question came up.

## 1. Where the 180-second limit is imposed

`slice/analyze_change.py`, `run_validation()`, lines 903–906:

```python
try:
    result = subprocess.run(
        v["command"], cwd=svc_dir, shell=True, capture_output=True, text=True, timeout=180, env=env,
    )
```

This is a single hardcoded literal (`180`) at one call site — not a named
constant, not a CLI flag, not an environment variable, not read from any
config file. There is no other reference to a validation-command timeout
anywhere in the file. (Two unrelated timeouts exist nearby and are **not**
in scope here: `npm install` gets its own 300-second limit at line 892,
and `git`/GitHub-API calls default to 30s/15s respectively — none of these
are what produced the Archify `ESCALATE`.)

When the command exceeds 180 seconds, `subprocess.run` raises
`subprocess.TimeoutExpired`, caught at lines 921–926:

```python
except subprocess.TimeoutExpired:
    outcomes.append({
        "target": v["target"], "command": v["command"], "result": "INCONCLUSIVE",
        "exit_code": None, "stdout_tail": "", "stderr_tail": "timed out",
        "classification": "INFRASTRUCTURE (timeout)",
    })
```

That outcome flows into `final_recommendation()`:

```python
any_inconclusive = any(o["result"] == "INCONCLUSIVE" for o in outcomes)
...
if any_inconclusive or no_validation_ran:
    return "ESCALATE", "Validation could not be completed (infrastructure/timeout or none available). Escalate for human review."
```

This branch is checked before risk level or confidence are consulted at
all — a timeout escalates unconditionally, regardless of how low-risk the
underlying change looks. That is the exact mechanism that produced the
Archify result.

**One related, real gap found while documenting this:** neither
`report.md` nor `audit.json` records the timeout value itself anywhere.
The report says `classification: INFRASTRUCTURE (timeout)`; nothing says
"180 seconds." An operator reading the report has no way to know the
actual limit without reading source code — which is exactly what this
diagnostic required. Any option below should also record the timeout
value used, in the outcome dict, so this stops being an implicit fact.

## 2. Does the timeout apply uniformly?

**Yes, confirmed by inspection — no exceptions exist anywhere.** The `180`
at line 905 is the only value used for every selected validation command
(`v["command"]`, e.g. `npm test`), for every target component, for every
repository this tool is ever pointed at. There is no per-repository,
per-command, per-organization, or per-invocation override mechanism of any
kind today. A fast unit-test suite and Archify's five-step, golden-image
render/build suite are held to the identical 180-second wall clock.

## 3. Evidence carried forward (Archify diagnostic)

| | |
| --- | --- |
| Current limit | 180s |
| Actual `npm test` duration | 338s (5m 38s real time) |
| Exit code | 0 |
| Tests | 723 passed, 0 failed, 25 skipped |
| Golden renders | all passed |
| `check:brand-marks` / `check:validators` / `check:release-identity` | all passed |

The original `INCONCLUSIVE (INFRASTRUCTURE/timeout)` was correct: nothing
about it misrepresented what happened. The resulting `ESCALATE` was driven
entirely by the timeout, not by any defect in the change under review.

## 4. Options considered

### A. Configurable global timeout
Add one new parameter (CLI flag and/or function argument, e.g.
`--validation-timeout-seconds`, **default unchanged at 180**), threaded
through to the single call site at line 905.

- **Smallest possible change**: one parameter, one call site.
- Default behavior is byte-for-byte identical unless the operator opts in.
- Fully preserves the timeout→`INCONCLUSIVE`→`ESCALATE` chain exactly as
  it exists today — only the numeric threshold moves, never the safety
  semantics.
- Weakness: it's a manual, per-invocation override. An operator has to
  already know (from a report like this one) that a given repository
  needs a longer window, and remember to pass it every time. It doesn't
  make the tool smarter about slow-but-healthy suites on its own.

### B. Per-repository/per-command timeout
A config file or lookup table mapping specific repositories or command
patterns to a longer timeout, maintained either in the target repository
or in ImpactTestAI's own repo.

- More precise in principle — a genuinely fast repo never waits longer
  than it needs to, and a genuinely slow one gets exactly what it needs.
- Real cost: requires a config schema, a storage location, and an
  ongoing maintenance story across however many pilot teams use this.
  This is the same shape of complexity the project has deliberately
  avoided everywhere else (no repository-specific rules in architecture
  discovery) — a per-repo timeout table is a per-repo exception list in
  a different costume, and it will drift stale exactly the way
  hardcoded architecture assumptions did.

### C. Staged timeout with an explicit `UNKNOWN` → retry path
On a first-attempt timeout, automatically retry once with a longer window
(e.g. 180s, then 600s on retry) before reporting `INCONCLUSIVE`.

- Adaptive with no configuration required — Archify would have gotten a
  real `PASSED` on the retry today, with zero operator involvement.
- Genuinely fast suites pay no penalty (they finish on the first
  attempt).
- Real cost: a suite that is *actually* hung (not just slow) now takes
  180s + 600s ≈ 13 minutes to report `ESCALATE` instead of 3 minutes —
  a real, non-trivial wall-clock cost for the failure case this timeout
  exists to bound in the first place. Also the largest code change of
  the four options (a retry loop, a second timeout value, a decision
  about whether `npm install` gets re-attempted too).
- Still fully preserves the never-fabricate contract — a retry that also
  times out still reports `INCONCLUSIVE`, never a guessed verdict.

### D. No timeout increase — clearer operator guidance only
Leave `180` exactly as it is; improve the report/audit output to state
the timeout value explicitly and suggest a next step (re-run locally with
more time; ask engineering to raise the limit for this repository).

- Zero code risk, zero new complexity, ships immediately.
- Does not solve the underlying problem: a repository whose *healthy*
  validation naturally takes longer than three minutes will report
  `ESCALATE` **every single time**, forever, regardless of how many times
  it's re-run — not because anything is wrong, but because the tool
  never gets to see the real result. That's a permanent ceiling on the
  tool's usefulness for an entire class of repository (anything with a
  render/build/golden-image step in its test suite, which is not a rare
  pattern).

## 5. Recommendation

**Option A (configurable global timeout, default unchanged), paired with
the report/audit transparency fix noted in §1 (record the timeout value
used), regardless of which option is chosen.**

Why this best fits the pilot's contract — *never convert incomplete
validation into PASS or FAIL* — better than the alternatives:

- It changes **only** the number fed into an already-safe mechanism. The
  `TimeoutExpired` → `INCONCLUSIVE` → `ESCALATE` chain is untouched
  end-to-end; there is no new code path that could accidentally start
  treating a timeout as a pass, a fail, or a probability input. Option C
  is the next-safest on this dimension (the retry's own timeout still
  routes through the identical `INCONCLUSIVE` handling), but it is a
  strictly larger change for a question — is 180s ever actually the
  *right* number for some repositories, or should it just be raised once
  and left alone? — that hasn't been answered yet. Answering that
  question is what Option A's real-world usage would tell us.
- It requires **zero speculative infrastructure** (no config schema, no
  per-repo storage, no retry-timing policy) for a problem currently
  evidenced by exactly one repository. Options B and C are both
  reasonable *next* steps if Option A's operator-supplied override turns
  out to be used often enough, across enough different pilot teams, to
  justify automating it — but building that now would be solving a
  problem based on a single data point.
- It does not silently cap the tool's usefulness the way Option D alone
  would, while adding negligible risk over Option D.

**Not recommended to combine with a default change:** the default should
stay 180s. Raising the default without evidence of how many pilot
repositories actually need longer would be exactly the kind of
un-investigated tuning this task was designed to prevent ("don't fix this
merely by raising the timeout").

## 6. What is explicitly deferred

- The actual `--validation-timeout-seconds` flag / parameter — not added
  in this round.
- Recording the timeout value in the outcome dict / report — not added in
  this round, though flagged in §1 as worth doing regardless of which
  timeout option is eventually chosen.
- Any decision about whether Option A's default should ever change.
- Options B and C, pending more evidence than one repository provides.

## 7. Test strategy

See `slice/tests/test_analyze_change.py` (new tests, added in this same
change; `analyze_change.py` itself is untouched). Since actually waiting
180+ real seconds in a test suite is impractical, timeout behavior is
exercised deterministically by mocking `subprocess.run` to raise
`subprocess.TimeoutExpired` — this tests the exact code path a real
timeout takes, without the wall-clock cost.

Three tests, each targeting a different part of the contract this
proposal must not weaken:

1. **`test_run_validation_reports_inconclusive_on_timeout`** — a timed-out
   command produces `result: "INCONCLUSIVE"` (never `"PASSED"` or
   `"FAILED"`), `exit_code: None`, and `classification: "INFRASTRUCTURE
   (timeout)"`.
2. **`test_run_validation_uses_the_current_hardcoded_180s_limit`** — pins
   the exact current value at the exact call site. This test is *expected*
   to need a deliberate update the moment Option A is actually
   implemented — it exists to make that change visible when it happens,
   not to block it.
3. **`test_timeout_outcome_never_reaches_accept_or_require_additional_validation`**
   — an `INCONCLUSIVE`/timeout outcome always produces `ESCALATE` from
   `final_recommendation()`, across every risk level and confidence
   combination — confirming a timeout can never be laundered into a
   different decision no matter what the rest of the assessment looks
   like.
