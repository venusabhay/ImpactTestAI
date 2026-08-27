# Artifact History & Reproducibility — Final Engineering Report

**Branch:** `feature/artifact-history` (pushed to `origin`, **not merged to `main`** — awaiting business review, per instruction)
**Implementation commit SHA:** `24fbb6e`
**Design (written before implementation):** [`slice/ARTIFACT_HISTORY_DESIGN.md`](../ARTIFACT_HISTORY_DESIGN.md)

---

## 1. Branching and baseline

- `feature/adapt-architecture-discovery` merged into `main` cleanly (merge commit `0a8b3b1`, no conflicts).
- Full v9 test suite (74 tests) confirmed passing on `main` post-merge.
- Accepted v9 baseline tagged: `architecture-discovery-v9-baseline` (pushed to `origin`).
- `feature/artifact-history` branched from that `main` and is where all of this milestone's work lives.
- `feature/adapt-architecture-discovery` was not touched after merging; it remains on `origin` as the historical record for that milestone, per your recommendation.

## 2. Tests: before / after

| | Count |
| --- | --- |
| Before (v9 baseline, `main`) | 74 |
| After (`feature/artifact-history`) | **89** (74 unchanged + 15 new) |

All 74 pre-existing tests pass unmodified. 15 new tests in `slice/tests/test_artifact_history.py` cover run identity and artifact immutability specifically (see §12 below for the mapping to each required proof).

## 3. Artifact storage approach

- New module `slice/artifact_history.py` owns: `run_id` generation, identity resolution (`organization`/`repository`/`repository_url`), base-ref-to-SHA resolution, and the write itself.
- `run_id = f"{utc_timestamp}-{uuid4_hex[:8]}"` — e.g. `20260828T221501Z-3f9a2c11`. The timestamp keeps runs sortable/readable; the random suffix is what actually guarantees uniqueness, so concurrent or identical-input executions never collide without any locking or shared counter. (Sequential numbering, `run-001`/`run-002`, was considered and rejected for exactly this reason — see design doc.)
- Directory layout, exactly as specified:

  ```
  artifacts/
    <organization>/
      <repository>/
        <run_id>/
          report.md
          audit.json
          metadata.json
  ```

- The run directory is created with `os.makedirs(..., exist_ok=False)` — this is the actual mechanism enforcing "never overwrite": since `run_id` is generated fresh in memory before any file exists, a genuine collision (practically impossible given the scheme above) raises `FileExistsError` rather than silently overwriting a prior run.
- No database, no dashboard, no index/manifest file. Listing a repository's history is `ls artifacts/<org>/<repo>/`.
- Existing `--out <path>` behavior is completely unchanged (still writes exactly one report/audit pair to the given path, for direct/ad-hoc use, exactly as every prior milestone's testing relied on). The new artifact-history write happens unconditionally, alongside it, controlled only by a new `--artifacts-root` flag (default `artifacts`).

## 4. Example historical run structure (real output from this branch)

```
artifacts/santiq/bulletproof-nodejs/20260827T200635Z-d5a774fc/audit.json
artifacts/santiq/bulletproof-nodejs/20260827T200635Z-d5a774fc/metadata.json
artifacts/santiq/bulletproof-nodejs/20260827T200635Z-d5a774fc/report.md
artifacts/santiq/bulletproof-nodejs/20260827T200657Z-9dac6af9/audit.json
artifacts/santiq/bulletproof-nodejs/20260827T200657Z-9dac6af9/metadata.json
artifacts/santiq/bulletproof-nodejs/20260827T200657Z-9dac6af9/report.md
```

Example `metadata.json` (real, from this branch's smoke test):

```json
{
  "run_id": "20260827T200635Z-d5a774fc",
  "organization": "santiq",
  "repository": "bulletproof-nodejs",
  "repository_url": "https://github.com/santiq/bulletproof-nodejs.git",
  "head_sha": "ffe0221ffe2945792be648de831c422cd934cbc5",
  "base_sha": "ffe0221ffe2945792be648de831c422cd934cbc5",
  "tool_version": "0.7.0-pilot",
  "policy_version": "repo-plus-ci-plus-cross-service-plus-discovery-v9",
  "started_at": "2026-08-27T20:06:35.817766+00:00",
  "completed_at": "2026-08-27T20:06:36.210011+00:00",
  "decision": "ESCALATE",
  "risk_level": "LOW"
}
```

`organization`/`repository`/`repository_url` are resolved with no manual input, in priority order: (1) `--github-repo owner/repo` if given, (2) `git remote get-url origin` if it parses as a GitHub remote, (3) an honest `"local"`/`<directory basename>` fallback with `repository_url: null` — never a fabricated identity.

## 5. Proof: repeated analysis does not overwrite history

Ran the identical command twice against the same repository/commit:

```
artifacts/santiq/bulletproof-nodejs/
  20260827T200635Z-d5a774fc/   <- first run
  20260827T200657Z-9dac6af9/   <- second run, ~22s later
```

Both directories, and all six files inside them, exist and are independently readable. The first run's `metadata.json` was re-read and confirmed byte-identical after the second run completed (test: `test_earlier_artifact_remains_unchanged_after_a_later_execution`).

## 6. Proof: the same commit can be analyzed twice, independently

`test_repeated_analysis_of_identical_commit_does_not_overwrite_or_deduplicate` runs the analyzer twice against a synthetic fixture with an identical `head_sha`, `base_sha`, `tool_version`, and `policy_version` on both runs, then asserts:

- both runs produced their own run directory (2 total, not 1),
- `head_sha`, `base_sha`, `tool_version`, `policy_version` are equal between the two runs' metadata (confirming the inputs really were identical), and
- `run_id` differs between them.

No deduplication occurs anywhere in the write path — there is no lookup-before-write step at all; every execution unconditionally gets a fresh `run_id` and a fresh directory.

## 7. Proof: report/audit/metadata stay consistent

`test_report_audit_and_metadata_belong_to_the_same_run` runs the analyzer twice, then for **every** run directory produced, asserts:

- `metadata.json`'s `run_id` equals the directory name,
- `audit.json`'s `run_id` (injected at write time) equals the directory name,
- `report.md`'s footer line contains that exact `Run ID: `<run_id>`.` string,
- `metadata.json`'s `decision`/`risk_level` agree with `audit.json`'s `recommendation.decision`/`risk.risk_level` for that same run.

This directly rules out the failure mode named in the milestone (`report.md` from run A, `audit.json` from run B, `metadata.json` from run C): there is no code path where the three files written by one `write_run_artifacts()` call could carry different `run_id` values, because all three are written from the same in-memory `run_id`/`audit_record`/`report` values within a single `main()` invocation.

## 8. GitHub Actions permission model / read-only confirmation

`.github/workflows/run-analysis.yml` (the target-repository pilot workflow) was updated to use `--artifacts-root` and to upload each run's artifacts named by its own `run_id` (`run-<run_id>`), eliminating any possibility of two different executions' uploaded artifacts being confused for each other.

**Nothing about permissions or the target checkout changed:**

- `permissions: contents: read` at the workflow level — unchanged.
- Target repository checkout — still `persist-credentials: false`, still checked out to an isolated `target-repo/` path, still never committed or pushed to.
- No new secrets, scopes, or tokens were introduced. `TARGET_REPO_TOKEN` (private-repo-only, read-only scopes) is unchanged.
- Artifact preservation uses `actions/upload-artifact@v4`, which requires no write access to any repository — it uploads to GitHub's own per-workflow-run artifact storage, not to a git commit.

## 9. Confirmation: risk/decision policy unchanged

- `build_risk_assessment()`, `final_recommendation()`, `build_validation_decision()` — **zero lines changed** (confirmed: `git diff main -- slice/analyze_change.py` shows no diff touching any of these function bodies).
- `design8.md` / `design9.md` (`design/design8.md`, `design/design9.md`) — **zero lines changed** (confirmed via `git diff main --stat`).
- `discovery.py` — **zero lines changed**.
- `TOOL_VERSION`/`POLICY_VERSION` were **not bumped** — correctly so, since no analysis rule changed. This milestone only adds a persistence/identity layer around the unchanged analysis pipeline.
- Stage 2 (CI history) and Stage 2B (cross-service validation) evidence categories are untouched and still kept clearly separate in both `report.md` and `audit.json` — nothing was collapsed or repurposed into a probability signal.

## 10. Limitations discovered

1. **A "no changes found" execution does not get a historical record.** If `get_change()` finds zero changed files against the given ref, `main()` exits with an error code before any report/risk/decision exists to record. This is a deliberate, minimal-scope choice, not an oversight: the required `metadata.json` fields (`decision`, `risk_level`) presuppose a completed analysis. Recording "the tool was invoked but there was nothing to analyze" as its own artifact type was judged out of scope for this milestone and is a candidate for later, smaller follow-up if it turns out to matter for pilot usability.
2. **`repository_url` is `null` when no `--github-repo` is given and no parseable GitHub remote exists** (e.g., a purely local repository, or a non-GitHub remote). This is the honest, disclosed outcome — not fabricated — but it does mean identity quality depends on how the analyzer is invoked. In the GitHub Actions pilot workflow, `--github-repo` is always supplied, so this only affects direct/local CLI use.
3. **Run history for a given repository is only as easy to browse as the filesystem it's on.** There's no cross-repository index (deliberately, per scope) — finding "all runs across all teams" requires listing `artifacts/*/*/*` rather than a single query. Acceptable for a pilot; a first candidate for a future milestone if/when a real product decision is made.

## 11. Overfitting / special-case audit

- `git diff main -- slice/artifact_history.py slice/analyze_change.py` contains **zero** references to any specific repository, organization, or filename used anywhere in this project's testing history (`social-media-mini`, `user-management-app`, `santiq/bulletproof-nodejs`, etc.) — confirmed both by direct inspection and by an automated test (`test_no_repository_specific_rules_in_artifact_history_module`) that greps the module's source for every repository name used across all rounds to date.
- Identity resolution operates purely on syntactic shape (a GitHub remote URL pattern, or the absence of one) — no hardcoded organization or repository name anywhere.

## 12. Definition-of-done checklist

| Requirement | Status |
| --- | --- |
| Every execution has a unique run ID | ✅ |
| Repository identity recorded | ✅ |
| Repository URL recorded | ✅ (honest `null` when genuinely unavailable) |
| Head SHA recorded | ✅ |
| Base SHA recorded | ✅ |
| Tool version recorded | ✅ (actual `TOOL_VERSION`, not hard-coded) |
| Policy version recorded | ✅ (actual `POLICY_VERSION`, not hard-coded) |
| Risk level and final decision recorded | ✅ |
| Report, audit JSON, metadata preserved together | ✅ |
| Historical executions cannot be overwritten | ✅ (`exist_ok=False`) |
| Repeated analysis of the same commit creates separate executions | ✅ (tested) |
| Artifacts internally consistent | ✅ (tested) |
| Previous artifacts unchanged after later runs | ✅ (tested) |
| GitHub Actions can execute against another repository | ✅ (workflow updated) |
| Target repositories remain read-only | ✅ (unchanged permissions/checkout) |
| Pilot users can retrieve/download historical artifacts | ✅ (named per run_id, 90-day retention) |
| Automated tests cover run identity and immutability | ✅ (15 new tests) |
| All existing v9 tests pass | ✅ (74/74) |
| Risk/decision logic unchanged | ✅ |
| Stage 2/2B evidence semantics unchanged | ✅ |
| `design8.md`/`design9.md` unchanged | ✅ |
| No production telemetry | ✅ |
| No new risk-scoring model | ✅ |
| No repository-specific architecture rules | ✅ |

## 13. Recommendation

**`PASS`**

Every acceptance criterion in the instruction was met without qualification, verified either by direct inspection (policy/design files unchanged) or by an automated test written specifically to prove it (run-identity, immutability, and cross-artifact consistency). The mechanism is deliberately minimal — no database, no dashboard, no index file — and adds nothing to the analysis pipeline itself; it only wraps the existing, unchanged pipeline with a persistence/identity layer.

---

Stopping here per instruction. `feature/artifact-history` is pushed to `origin` and awaiting business review; it has not been merged into `main`. No further milestone has been started.
