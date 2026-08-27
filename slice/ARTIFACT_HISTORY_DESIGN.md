# Artifact History & Reproducibility (design)

**Status: design, written before implementation.** Scope: preserve every
analysis execution as an immutable, independently traceable historical
record. This does **not** touch `design8.md`, `design9.md`, the risk/decision
policy (`build_risk_assessment()`, `final_recommendation()`, probability
semantics, `ESCALATE`/`REQUIRE_ADDITIONAL_VALIDATION`/`ACCEPT` rules), or
architecture discovery (`discovery.py`).

## What already exists (reuse, don't duplicate)

`analyze_change.py`'s `audit_record` already captures most of the identity
concepts this milestone needs:

| Concept | Existing field | Notes |
| --- | --- | --- |
| Head commit | `change["repo_head"]` (`git rev-parse HEAD`) | Already a resolved 40-char SHA. Reused directly as `head_sha`. |
| Base ref (as given) | `change["base_ref"]` / `audit_record["base_ref"]` | The raw `--against` string (`"HEAD"`, a branch name, `"origin/main"`, or already a SHA) -- **not** necessarily resolved to a SHA. Kept as-is; a new `base_sha` is added alongside it (see below), not a replacement. |
| Tool version | `TOOL_VERSION` / `audit_record["tool_version"]` | Reused verbatim. |
| Policy version | `POLICY_VERSION` / `audit_record["policy_version"]` | Reused verbatim. |
| Decision | `recommendation[0]` / `audit_record["recommendation"]["decision"]` | Reused verbatim. |
| Risk level | `risk["risk_level"]` | Reused verbatim. |
| A single timestamp | `audit_record["generated_at"]` | Kept as-is in `audit.json` (unchanged contract); the same moment's value is also used for `metadata.json`'s `completed_at` rather than computing it twice independently. |

New concepts this milestone actually needs to add: `run_id`,
`organization`, `repository`, `repository_url`, a resolved `base_sha`, and
`started_at` (captured at the top of `main()`, before any work begins).

## `run_id`: unique, not timestamp-alone

```
run_id = f"{utc_now:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
```

e.g. `20260828T221501Z-3f9a2c11`. A timestamp component keeps run IDs
sortable and human-readable; the random suffix is what actually guarantees
uniqueness -- it means two executions started in the same second (or two
concurrent CI jobs) never collide, with no coordination, locking, or shared
counter required. This was chosen over sequential numbering (`run-001`,
`run-002`, ...) specifically because a sequential counter requires either a
lock or a race-prone "count existing directories and add one" read, and a
pilot running from multiple teams' CI jobs simultaneously cannot assume
serialized access to shared storage. Directories still sort chronologically
by name, so listing a repository's run history in order needs no extra
index file.

## Directory layout

```
artifacts/
  <organization>/
    <repository>/
      <run_id>/
        report.md
        audit.json
        metadata.json
```

Exactly the structure the milestone recommends. `artifacts_root` defaults
to `artifacts` (relative to the current working directory, matching how
`--out` already defaults to a relative `report.md`) and is overridable via
`--artifacts-root` for tests and for callers who want a different location.

The run directory is created with `exist_ok=False`: if a collision ever
occurred (which the run_id scheme makes practically impossible), directory
creation raises rather than silently overwriting a prior run's files. This
is the core mechanism enforcing "never overwrite."

## Identity resolution (`organization` / `repository` / `repository_url`)

In priority order:

1. **`--github-repo owner/repo`** (already an existing, optional flag used
   for CI-history fetching) -- if given, `organization=owner`,
   `repository=repo`, `repository_url=https://github.com/owner/repo`.
2. **`git remote get-url origin`** in the target repository, if it parses
   as a GitHub SSH or HTTPS remote -- `repository_url` is the remote URL
   exactly as git reports it (not reconstructed/guessed), and
   `organization`/`repository` are parsed from it.
3. **Fallback**: `organization="local"`, `repository=<basename of the
   target repo's absolute path>`, `repository_url=None`. This is an honest
   "no remote identity available" outcome -- consistent with this
   project's existing rule of reporting insufficient evidence rather than
   fabricating it -- not a guess.

## `metadata.json` contract

Exactly the fields the milestone specifies, sourced from values already
computed by the existing pipeline (see table above) plus the four new
identity/timing fields:

```json
{
  "run_id": "20260828T221501Z-3f9a2c11",
  "organization": "acme-co",
  "repository": "payment-service",
  "repository_url": "https://github.com/acme-co/payment-service",
  "head_sha": "a1b2c3d4...",
  "base_sha": "e5f6a7b8...",
  "tool_version": "0.7.0-pilot",
  "policy_version": "repo-plus-ci-plus-cross-service-plus-discovery-v9",
  "started_at": "2026-08-28T22:14:58.001+00:00",
  "completed_at": "2026-08-28T22:15:01.442+00:00",
  "decision": "ESCALATE",
  "risk_level": "HIGH"
}
```

## Cross-artifact consistency

- `run_id` is injected into `audit_record` (`audit_record["run_id"]`) so
  `audit.json` is self-identifying even if separated from the other two
  files.
- `report.md`'s existing footer line (`*Tool version: ... Risk/validation
  rules: ...*`) gains a leading `Run ID: `<run_id>`.` clause, for the same
  reason in the human-readable artifact.
- `metadata.json` is, by construction, the last of the three files written,
  and all three are written from the same in-memory `run_id`,
  `audit_record`, and `report` values within one `main()` invocation -- there
  is no code path that can produce a report/audit/metadata triple stamped
  with different run IDs.

## What this deliberately does not do

- No database, no dashboard, no index/manifest file aggregating runs
  (`ls artifacts/<org>/<repo>/` already lists them; a separate index would
  be one more piece of mutable shared state to get wrong).
- No change to `build_risk_assessment()`, `final_recommendation()`,
  probability semantics, or any threshold.
- No change to `discovery.py` or the architecture-discovery scope.
- No deduplication of identical-input runs -- two executions of the same
  repo/head/base/tool/policy still get two run IDs and two preserved
  artifact sets, by design (this is required, not an oversight).
- No new GitHub Actions permissions. The target-repository checkout
  remains `persist-credentials: false` with `permissions: contents: read`;
  artifact preservation uses `actions/upload-artifact`, which requires no
  additional scope.
