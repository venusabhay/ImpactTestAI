# Pipeline fail-safe: design (written before implementation)

**Scope:** the two unhandled crashes found during the pilot run
(`slice/reports/pilot-runs/PILOT_FINDINGS_REPORT.md`, §2). No risk,
discovery, or recommendation policy is touched.

## 1. Exact failure points

### `npm install` timeout — `run_validation()`, `analyze_change.py`

```python
install = subprocess.run(
    "npm install", cwd=svc_dir, shell=True, capture_output=True, text=True, timeout=300, env=env,
)
if install.returncode != 0:
    outcomes.append({... "INFRASTRUCTURE (dependency install failed)" ...})
    continue
```

The non-zero-exit-code case is already handled and already produces a
normal, complete report (this exact path has worked correctly since Stage
2's introduction of `--npm-install`). There is no `try`/`except` around
the call at all, so `subprocess.TimeoutExpired` — confirmed to actually
occur in the pilot, since this specific dependency tree took ~360
real-world seconds against a 300-second limit — propagates out of
`run_validation()`, out of `main()`, and crashes the process. No
`report.md`, no `audit.json`, nothing.

### CI-history network failure — `fetch_ci_history()` / `_gh_api_get()`

```python
try:
    runs_data = _gh_api_get(...)
except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
    record["error"] = f"{type(e).__name__}: {e}"
    ...
    return record
```

This function was already built defensively — it already catches four
specific exception types, at *two* call sites (the initial run-list fetch,
and the per-run job-detail fetch inside the loop), and the second site
already preserves whatever evidence was collected from earlier runs in
the same loop before appending a `limitations` entry and `continue`-ing.
The gap is narrower than it first appears: `http.client.IncompleteRead`
(observed in the pilot) is not a subclass of any of the four caught types
— it derives from `http.client.HTTPException`, not `OSError`/`URLError`
— so it was never caught, and it crashed `main()` the same way the
`npm install` timeout did.

**Consequence of this being narrower than expected:** most of what the
milestone instruction asks for (distinguish "not found" from "could not
retrieve"; preserve partial evidence; surface the failure in `report.md`
and `audit.json`; never fabricate) is *already implemented and already
correct* — confirmed by re-reading `fetch_ci_history()`'s existing
`available`/`error`/`limitations` fields and `render_report()`'s existing
`if not hist["available"]:` branch, which already renders exactly this
distinction. The actual code change needed is to widen the two `except`
clauses to also catch the exception that was observed (and its natural
siblings), not to rebuild this machinery.

## 2. Investigation: `shell=True` + `timeout=` semantics

Observed in the pilot: after the `npm install` `TimeoutExpired` fired
(crashing that run), a *second* attempt against the same checkout
completed quickly and successfully — because `node_modules` already had
678 of the eventual 757 packages, despite Python having given up on the
first attempt roughly 300 seconds in. Independently reproduced: a plain,
unassisted `npm install` in a fresh copy of the same checkout took **6
minutes real time** with no interruption.

**Why this happens, and why it isn't being changed here:**
`subprocess.run(cmd, shell=True, timeout=N)` spawns `/bin/sh -c "<cmd>"`
as the direct child process. When the timeout fires, Python kills *that*
process (the shell). It does not kill the shell's own children — here,
the actual `npm` process, and whatever `node`/network processes `npm`
itself forks — unless they happen to die when their parent does (they
don't, on POSIX, unless explicitly placed in the same process group and
that group is signaled). This is a well-known, general property of
`subprocess.run(shell=True, timeout=...)`, not a bug specific to this
codebase.

The correct general fix (running the child in its own process group via
`start_new_session=True` and killing the whole group with `os.killpg()` on
timeout) is a real, well-understood technique — but it is a change to
process-management semantics, exactly what this milestone was told not to
casually make. It would also apply identically to the *validation*
command's own `subprocess.run(..., shell=True, timeout=validation_timeout_seconds, ...)`
call, which is explicitly out of scope for this milestone ("do not change
the existing validation-command timeout behavior"). Changing it for
`npm install` alone while leaving the validation command's identical
pattern untouched would be an inconsistent half-fix; changing both is a
larger, more consequential change than "harden two failure paths" calls
for.

**Decision: document only, change nothing about process-group handling.**
The `TimeoutExpired` catch added below stops the *analysis* from waiting
indefinitely and correctly reports `INCONCLUSIVE` — it does not, and is
not claimed to, guarantee the underlying `npm install` process tree is
actually gone. That gap is now written down (in code comments and here)
rather than silently rediscovered next time.

## 3. Fix design

### `npm install`

- Wrap the existing `subprocess.run("npm install", ...)` call in
  `try`/`except subprocess.TimeoutExpired`.
- On timeout: append an outcome with `result: "INCONCLUSIVE"`,
  `exit_code: None`, and a **new, distinct** classification,
  `"INFRASTRUCTURE (dependency install timed out)"` — kept separate from
  the existing `"INFRASTRUCTURE (dependency install failed)"` (non-zero
  exit) string, so a report or audit reader can tell the two apart
  (per the milestone's explicit "preserve the distinction" requirement).
  Then `continue` — the existing, unchanged behavior for the
  non-zero-exit case — so validation is never attempted against
  dependencies known to be unavailable.
- The `300` literal becomes a named constant
  (`NPM_INSTALL_TIMEOUT_SECONDS`), referenced both by the `subprocess.run`
  call and recorded on the outcome (`install_timeout_seconds`) — the same
  pattern already used for the validation-command timeout, applied to the
  one place it was missing. No CLI flag is added for this value: the
  milestone asks only that failure be handled safely and the value be
  visible in output, not that it become configurable — adding a flag here
  would be scope beyond what was asked.
- `render_report()` gains one line, symmetric with the existing
  `timeout_seconds` line, to surface `install_timeout_seconds` when
  present.

### CI history

- Add `import http.client` and widen both `except` tuples in
  `fetch_ci_history()` to add `http.client.HTTPException` (the parent of
  the observed `IncompleteRead`, so related `http.client`-level failures
  are covered by the same fix rather than requiring a new patch per
  subtype) and the built-in `ConnectionError` (covers
  `ConnectionResetError`/`ConnectionAbortedError`/`BrokenPipeError`/
  `ConnectionRefusedError` — the other common "the network dropped"
  shapes, distinct from `IncompleteRead` specifically).
- No other change: the `available`/`error`/`historical_signal`/
  `limitations` fields, the "no CI job matching this service was found"
  vs. "could not reach the GitHub Actions API" distinction, and partial
  per-run evidence preservation are all pre-existing and already correct
  once the exception is actually caught.

## 4. What this explicitly does not touch

`build_risk_assessment()`, `final_recommendation()`, `build_impact_assessment()`,
`POLICY_VERSION`, `RISK_PATTERNS`, `SENSITIVE_PATH_HINTS`, the
`INCONCLUSIVE`→`ESCALATE` rule, CI-evidence weighting (still additive-only,
never fed into probability/risk_level), the validation-command timeout
(`validation_timeout_seconds`) and its own `except subprocess.TimeoutExpired`
handling, the CI-history workflow-filename assumption, environment-variable
classification, `passport.ts`-style discovery, `ACCEPT` reachability, and
CI rate-limit mitigation. All remain exactly as documented in prior
reports, deliberately deferred.
