# Repository organization: disposition

**Branch:** `chore/repository-organization`, from `main` @ `da3d6d8`.
**Scope: hygiene only.** No Python behavior, workflow logic, policy,
risk scoring, or discovery changed — verified in §5. This is a file
reorganization plus reference/link corrections made necessary by it.

## 1. The problem

By this point the repository had accumulated design docs, milestone
proposals/dispositions, and pilot evidence (case reports, investigation
findings, audit output) scattered across `design/`, `slice/`, and
`slice/reports/` — mixed directly alongside the product source. Nothing
was wrong with any individual document; the accumulation itself had
become the problem, per the engineering instruction that started this
branch.

## 2. Inventory and categorization

Every tracked `.md` file, every generated artifact (`.audit.json`,
`.patch` fixtures), and the one untracked audit document
(`REPOSITORY_HYGIENE_AUDIT.md`) and untracked pilot-round directory
(`slice/reports/pilot-runs/`) were inventoried and placed into one of:

- **Product documentation** — stays in place or moves only to match the
  requested top-level layout (`PILOT.md` to the repository root).
- **Engineering decision/history** — design docs written before
  implementation, proposals, dispositions, and the sequential
  architecture narrative → `docs/design/`, `docs/decisions/`.
- **Pilot evidence** — case results, investigation rounds, summary
  reports → `pilot/cases/`, `pilot/investigations/`, `pilot/reports/`.
- **Generated artifact** — nothing found tracked in git under this
  category; the existing `artifacts/.gitignore` pattern already covered
  it. Added `artifacts/README.md` (with a `.gitignore` exception) so the
  directory's purpose is documented and it survives a fresh checkout.
- **Obsolete/duplicate** — none found. Nothing was deleted.

No file's content was rewritten to fit the new structure, beyond the
path corrections in §4. Historical documents (milestone reports, audit
output, generated report snapshots) keep the substance they had when
written — moving a document is not the same as re-authoring it, and
none of this milestone's instructions asked for the latter.

## 3. What moved where

| From | To |
|---|---|
| `design/business-vision.md`, `design/design1.md`–`design9.md` | `docs/design/` (same filenames) |
| `slice/ARCHITECTURE_DISCOVERY_DESIGN.md`, `ARTIFACT_HISTORY_DESIGN.md`, `ROUTE_DISCOVERY_MULTILINE_DESIGN.md`, `PIPELINE_FAIL_SAFE_DESIGN.md`, `VALIDATION_TIMEOUT_PROPOSAL.md`, `VALIDATION_TIMEOUT_DISPOSITION.md` | `docs/decisions/` (same filenames) |
| `REPOSITORY_HYGIENE_AUDIT.md` (untracked, root) | `docs/decisions/REPOSITORY_HYGIENE_AUDIT.md` (now tracked, with a historical-context header added — see §4) |
| `slice/PILOT.md` | `PILOT.md` (repository root) |
| `slice/PILOT_FEEDBACK_TEMPLATE.md` | `pilot/PILOT_FEEDBACK_TEMPLATE.md` |
| `slice/reports/ARTIFACT_HISTORY_final_report.md` | `pilot/reports/ARTIFACT_HISTORY_final_report.md` |
| `slice/reports/vertical-slice-package.md`, `verify-cache-change-report.{md,audit.json}` | `pilot/cases/` (kept together — see §4, "co-location") |
| `slice/reports/adapt-architecture-discovery/` (all v5–v9 content, held-out results, regression verification, `NEXT_MILESTONE.md`) | `pilot/investigations/architecture-discovery/` (moved as one atomic unit, internal structure unchanged) |
| `slice/reports/user-management-app-pilot/` | `pilot/cases/user-management-app-pilot/` (moved as one atomic unit) |
| `slice/reports/pilot-runs/` (untracked) | `pilot/cases/2026-08-28-pilot-round/` (now tracked) |

`slice/reports/` itself was **not** deleted — see §4.

## 4. Deliberate choices and deviations from the illustrative examples

- **Original filenames preserved**, not renamed to the shorter
  illustrative names in the instruction (e.g. `validation-timeout.md`).
  Two distinct documents exist for that topic (the proposal and the
  disposition) and both are genuinely worth keeping — renaming and/or
  merging them risked losing that distinction or breaking more inbound
  references than necessary for a hygiene-only change. Every file kept
  its exact original name; only its directory changed.
- **`vertical-slice-package.md` co-located with
  `verify-cache-change-report.{md,audit.json}` under `pilot/cases/`**,
  not split into `pilot/reports/` as an initial read of the categories
  suggested. The two documents cross-reference each other by relative
  link and describe the same underlying evidence from two angles;
  splitting them would have broken that relationship for no benefit.
- **`slice/reports/` was not deleted.** `.github/workflows/pilot-ci.yml`
  and `run-analysis.yml` write their generated (already-`.gitignore`d)
  smoke-test/run output to hardcoded `slice/reports/pilot-*` paths, and
  `analyze_change.py`'s `--out` handling does not create missing parent
  directories — removing this directory would break `pilot-ci.yml` on
  the next fresh checkout. It now contains only a `README.md` explaining
  this narrow remaining purpose. Verified directly: re-ran the exact
  command sequence `pilot-ci.yml` runs (fixture build → analyze →
  artifact checks) against the reorganized tree; it completed
  successfully and produced valid `report.md`/`audit.json` output in
  that location (see §5).
- **`.github/workflows/*.yml` were not modified at all**, including
  comments that mention old paths (`run-analysis.yml`'s comments
  mentioning `slice/PILOT.md`, `slice/VALIDATION_TIMEOUT_PROPOSAL.md`,
  `slice/VALIDATION_TIMEOUT_DISPOSITION.md`). The instruction was
  explicit that workflows are out of scope for this milestone; those
  three comment lines are now stale and are flagged here as a known,
  intentionally-deferred follow-up rather than fixed in place.
- **Historical generated report bodies were not edited.** Many files
  under `pilot/investigations/architecture-discovery/` and
  `pilot/cases/2026-08-28-pilot-round/` contain the literal text
  `analyze_change.py` generated at the time they were run, including
  `(see slice/ARCHITECTURE_DISCOVERY_DESIGN.md)` phrasing that reflects
  the tool's path convention *at that historical moment*. These are
  frozen point-in-time snapshots, the same way a screenshot isn't
  updated when the UI changes later — editing their body text would
  misrepresent what the tool actually said when it ran. Only the *live*
  source of that text — the f-string in `analyze_change.py` that
  generates all *future* reports — was updated (see §5), so new reports
  point to the correct current location.
- **`docs/architecture/` created with only a placeholder README.** No
  document in the repository is a maintained, current-state-only
  architecture reference distinct from the historical `design/`
  narrative; nothing was invented to fill it.
- **`REPOSITORY_HYGIENE_AUDIT.md` kept as historical record, with a
  header note added** pointing at this document and the new top-level
  READMEs, since its own content (an inventory of file locations) is
  now doubly stale — once from the fixes it already led to, and again
  from this reorg. The note is additive (a blockquote at the top); the
  audit's original findings are untouched.

## 5. Verification

- **Full test suite:** `python3 -m pytest tests/ -q` — **113/113 pass**,
  both before and after every content edit in this branch.
- **No behavior/policy change:** `git diff` against every `.py` file in
  this branch touches only comment text and one f-string literal (a
  documentation-pointer path inside a generated-report string); every
  changed line is a `slice/FOO.md` → `docs/decisions/FOO.md` path
  substitution, nothing else. Confirmed line-by-line (see the branch's
  own diff for `slice/analyze_change.py`, `discovery.py`,
  `artifact_history.py`, and the three test files).
- **`POLICY_VERSION`, risk scoring, discovery, `final_recommendation()`:**
  unchanged (not present in any diff in this branch).
- **Link integrity:** every relative Markdown link (`](...)`) in every
  tracked `.md` file in the repository was resolved programmatically
  against its file's location; all resolve to an existing file (the one
  non-match found was a `re.compile()` regex snippet inside
  `ROUTE_DISCOVERY_MULTILINE_DESIGN.md` that a naive `]( )` scan
  mistook for a link — not an actual reference).
- **`pilot-ci.yml` compatibility:** manually re-ran that workflow's exact
  step sequence (`slice/fixtures/setup_fixture.sh`, then
  `analyze_change.py ... --out slice/reports/pilot-ci-smoke-report.md`,
  then the artifact-existence and JSON-parse checks) against the
  reorganized tree — completed successfully, produced a valid
  `report.md`/`audit.json`, `TOOL_VERSION` unchanged
  (`0.10.0-pilot`). Generated output was then removed (already
  `.gitignore`d, per existing patterns).
- **`.gitignore`:** `artifacts/*` with a `!artifacts/README.md`
  exception (previously `artifacts/` blocked everything unconditionally,
  which would also have blocked the new README). Verified with
  `git check-ignore` that `artifacts/README.md` is tracked while
  everything else under `artifacts/` remains ignored.

## 6. What was retained, archived, or deleted

- **Retained, unchanged in substance:** every design doc, decision doc,
  pilot case, and investigation report that existed before this branch.
- **Archived:** nothing separately archived — everything retained is
  simply relocated, per §3.
- **Deleted:** nothing.

## 7. Known follow-ups (not done here, out of scope)

- `run-analysis.yml`'s three comments mentioning pre-move paths
  (§4) — a workflow-file edit, deferred.
- `REPOSITORY_HYGIENE_AUDIT.md`'s own internal file-path claims are now
  additionally stale (describing a structure two reorgs old); flagged
  via the header note in §4 rather than rewritten.
