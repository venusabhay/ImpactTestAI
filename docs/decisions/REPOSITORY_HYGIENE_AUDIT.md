# Repository Hygiene & Documentation Audit

> **Note:** this audit reflects the repository structure as it existed
> before the `chore/repository-organization` reorg (see
> `docs/decisions/REPOSITORY_ORGANIZATION_DISPOSITION.md`). File paths
> mentioned below (`slice/reports/...`, `design/...`, `slice/PILOT.md`,
> etc.) describe where things were at audit time and may no longer
> exist at those locations. See [`docs/README.md`](../README.md) and
> [`pilot/README.md`](../../pilot/README.md) for the current structure.
> The 4 HIGH-priority findings this audit led to were fixed separately
> (see the `feature/repository-hygiene` merge); this document is kept as
> the historical record of that review, not as a current file map.

**Audit performed against:** `main` @ `659aa48a01b58ef7fd4215ddfd8104b143ed5a5a`
**Baseline tags present:** `architecture-discovery-v9-baseline`, `artifact-history-baseline`
**Current test count:** **89 passing** (`python3 -m pytest slice/tests/`) — this is the *current* count; any other count appearing below (24, 42, 47, 57, 66, 74) is quoted *only* where it appears inside a dated, historical milestone report describing that report's own point in time, and is correct in that context.
**Read-only audit:** no implementation, design, policy, or CI files were changed to produce this report. See §11 for the verification.

This report is an inventory, not a set of applied changes. Every row separates **Fact** (what is currently true on disk) from **Recommendation** (what engineering suggests). No file listed here has been modified.

---

## 1. Findings table

| File | Status | Problem | Evidence | Recommended action | Priority |
| --- | --- | --- | --- | --- | --- |
| `README.md` | **OUTDATED** | Fact: line 17 states "It currently assumes a `services/<name>/` repository layout." Recommendation: this has not been true since `ADAPT_ARCHITECTURE_DISCOVERY` v5; the accepted v9 baseline discovers components from `package.json` presence anywhere and routes from any `receiver.method(path, ...)` call. | `slice/discovery.py` (`find_components`, `find_route_registrations`); contradicts `slice/PILOT.md` line 66, which already states the corrected behavior. | Replace the sentence with language consistent with `slice/PILOT.md`'s already-corrected description, or simply link to it instead of restating (avoids the two docs drifting again). | **HIGH** |
| `slice/README.md` (line 19) | **OUTDATED / INCONSISTENT** | Fact: a leftover paragraph from the v5 round still says `ADAPT_ARCHITECTURE_DISCOVERY (evaluated; current milestone; on feature/adapt-architecture-discovery, not merged)` and `Recommendation: NEEDS_MORE_WORK`, directly contradicting the correct, up-to-date status one paragraph above it (line 5: "v9 accepted as the baseline on `main`... `PASS`"). Recommendation: this paragraph was never updated across the v6/v7/v8/v9 rounds and now contradicts the document's own banner. | Compare line 5 vs line 19 in the same file; branch `feature/adapt-architecture-discovery` is in fact merged (`0a8b3b1`) and tagged. | Remove or rewrite this paragraph — either fold its useful content (the description of what changed) into a proper "Architecture Discovery v5–v9" narrative section (see next row), or delete it now that the v5–v9 story is fully told in the linked final reports. | **HIGH** |
| `slice/README.md` (§"What's here", lines 39–44) | **OUTDATED / MISSING** | Fact: only lists `analyze_change.py` and the three original Stage-1 report files. Recommendation: doesn't mention `discovery.py`, `artifact_history.py`, `slice/tests/`, `slice/fixtures/`, `slice/PILOT.md`, or any of the design docs added since. | `git ls-files slice/` vs. this section's contents. | Rewrite this section to reflect the current file set, or replace it with a link to the "Repository layout" section already present in the root `README.md` (avoids maintaining the list twice). | **HIGH** |
| `slice/README.md` (lines 48, 87) | **REVIEW** | Fact: hardcodes a local filesystem path — `` `/Users/abhay/git-venusabhay/social-media-mini` `` — as "the canonical local location for this repo." Recommendation: meaningless (and slightly confusing) to any other engineer or team; this is a single developer's machine path baked into checked-in documentation. | Literal string in the file. | Replace with a plain reference to the public repo URL (`https://github.com/venusabhay/social-media-mini`), which is already given once earlier in the same section. | **MEDIUM** |
| `slice/README.md` (§"How to reproduce", lines 54–61) | **MISSING** | Fact: the CLI usage example does not mention `--artifacts-root`, and the surrounding text never explains the run-history/`metadata.json` behavior that Artifact History added. Recommendation: an engineer reading this section would not know every invocation now produces a persistent, versioned run record. | `slice/analyze_change.py`'s `--artifacts-root` flag (added in the Artifact History milestone); absent from this example. | Add the flag to the example and a one-line pointer to `ARTIFACT_HISTORY_DESIGN.md`. | **MEDIUM** |
| `slice/README.md` (title, line 1) | **REVIEW** | Fact: titled "Vertical Slice — First Implementation Milestone." Recommendation: the document now covers Stage 1 through Artifact History — seven-plus milestones, not "the first" — and a new reader could reasonably assume this is a narrow, single-purpose doc rather than the project's running engineering log. | Document scope vs. title. | Retitle (e.g. "Vertical Slice — Engineering History") or leave as-is if the team considers "first implementation milestone" a fixed proper-noun name for Stage 1 specifically and wants a *separate* running log — this is a product-position call, not an engineering one (see §7). | **LOW** |
| `slice/reports/vertical-slice-package.md` (banner, lines 3–4) | **OUTDATED** | Fact: the banner reads `STATUS: Stage 2B — Officially Accepted (frozen, no further work pending Stage 3 decision)`. Recommendation: work has since proceeded through Stage 2C and the full `ADAPT_ARCHITECTURE_DISCOVERY`/`ARTIFACT_HISTORY` sequence; this reads as if the project stalled after Stage 2B awaiting a decision that was made long ago. | `main`'s current tags/history vs. this banner; linked from `slice/README.md` as a "business-readable package." | Update the banner to reflect current status, or add a dated addendum noting the banner is a frozen point-in-time snapshot of the Stage 2B acceptance specifically (the rest of the document's content about Stage 2B itself is accurate and should be kept). | **HIGH** |
| `slice/reports/adapt-architecture-discovery/NEXT_MILESTONE.md` | **OUTDATED** | Fact: states "No implementation work has started on this" about the comment-awareness/controller-method-tracing milestone. Recommendation: that work was fully completed in v7 (three milestones ago). This is a direct hit on the audit's own example of a stale claim ("not started" where no longer true). | `ADAPT_ARCHITECTURE_DISCOVERY_v7_final_report.md` documents exactly this work as done. | Add a one-line "Superseded by v7" note at the top rather than deleting — this document is legitimate historical evidence of a real business decision point and should be preserved, just clearly marked as resolved. | **HIGH** |
| `slice/reports/adapt-architecture-discovery/regression-verification/` and `held-out-results/` (unversioned dirs) | **REVIEW** | Fact: these two directories hold the v5-round's freeze-verification and held-out evidence, but — unlike every later round (`-v6`, `-v7`, `-v8`, `-v9`) — they carry no version suffix. Recommendation: a reader browsing `slice/reports/adapt-architecture-discovery/` would reasonably wonder whether these are duplicates of the versioned ones rather than the (distinct, older) v5 data they actually are. | Directory listing; content diff against `-v6` confirms distinct, older timestamps/PIDs, not a duplicate. | Rename to `regression-verification-v5/` and `held-out-results-v5/` for consistency (content unchanged, historical evidence preserved either way). | **LOW** |
| `slice/reports/adapt-architecture-discovery/ADAPT_ARCHITECTURE_DISCOVERY_report.md` | **REVIEW** | Fact: this is the v5 final report, named without a version number, while v6 onward all follow `..._v{N}_final_report.md`. Recommendation: same naming-consistency gap as above. | Filename pattern comparison. | Optionally rename to `ADAPT_ARCHITECTURE_DISCOVERY_v5_final_report.md` and update the two inbound links (root banner already links here; `slice/README.md` line 19's stale paragraph also links here). | **LOW** |
| `slice/reports/user-management-app-pilot/RERUN_ACCEPTANCE_CRITERIA.md` | **MISSING** | Fact: defines the acceptance criterion for the "next" architecture-discovery capability but has no note that this criterion was in fact satisfied (re-run unchanged in v5 and reverified through v9). Recommendation: not factually wrong, just incomplete — a reader today can't tell from this file alone that the criterion was met. | `regression-verification-v9/change-a-rerun.md`, `change-b-rerun.md`, `change-c-rerun.md` show the criterion satisfied. | Add a short "Status: satisfied as of v5, reverified through v9 — see regression-verification-v9/" note at the top. | **LOW** |
| `.github/workflows/run-analysis.yml` | **REVIEW** | Fact: if `analyze_change.py` exits 1 (the documented "no changes found" case), `RUN_ID`/`RUN_DIR` are never set, and the subsequent "Upload this run's artifacts" step (`if: always()`) still runs with an empty `run_id`/path. Recommendation: this failure path isn't tested or documented — `slice/PILOT.md`'s "If something goes wrong" section doesn't mention it. | Reading the job's step dependencies; `main()`'s `sys.exit(1)` on no changed files (`analyze_change.py`). | Either add a guard so the upload step is skipped cleanly when no run was produced, or document the resulting failure mode explicitly in `PILOT.md`. This is a business/engineering judgment on how much to invest in an edge case, not applied here. | **MEDIUM** |
| `.github/workflows/run-analysis.yml` | **REVIEW** | Fact: `base_ref` defaults to `"main"`. Recommendation: a target repository whose default branch is `master` (or anything else) and whose user doesn't override `base_ref` will fail at the "Fetch base ref for diffing" step with no repository-specific guidance. | `on.workflow_dispatch.inputs.base_ref.default` vs. `git fetch origin "${{ inputs.base_ref }}"`. | Note this explicitly in `slice/PILOT.md`'s `base_ref` row ("usually `main` — if your repository's default branch is `master`, use that instead"). | **MEDIUM** |
| `.github/workflows/pilot-ci.yml` | **REVIEW** | Fact: the CI smoke test still only exercises `--out` and checks for `.md`/`.audit.json` — it never invokes `--artifacts-root` or asserts a `metadata.json`/`run_id` was produced. Recommendation: the smoke test doesn't cover the Artifact History behavior it's meant to be smoke-testing "the whole pipeline," per its own comment on line 4. | File contents vs. `slice/tests/test_artifact_history.py` (which does cover this, but only as unit/subprocess tests, not as part of the CI smoke-test job). | Add `--artifacts-root` to the smoke-test invocation and assert a `metadata.json` was produced, matching what `run-analysis.yml` now does. | **MEDIUM** |
| `slice/PILOT.md` (line 59) | **INCONSISTENT** (documentation vs. code — reported per §6/§9, not fixed) | Fact: lists three possible final recommendations, including "**proceed**" (i.e. `ACCEPT`). Recommendation: under the current, unmodified risk/decision policy, `ACCEPT` is structurally unreachable — `final_recommendation()`'s `probability_confidence` is hardcoded to `"LOW"` always, so `risk["confidence"]["overall"]` is always `"LOW"`, and the `if overall == "LOW": return REQUIRE_ADDITIONAL_VALIDATION` branch fires before the `ACCEPT` fallback can ever be reached. Confirmed empirically: grepping every report this project has ever generated for `"ACCEPT"` as a decision returns zero matches. | `slice/analyze_change.py`, `build_risk_assessment()` lines defining `probability_confidence = "LOW"` (always) and `final_recommendation()`'s branch order; corpus-wide grep of `slice/reports/**/*.md` and `*.audit.json`. | **This is a documentation-vs-code disagreement, reported as instructed, not silently fixed.** Whether to (a) correct the documentation to describe only the two decisions that actually occur, or (b) treat this as a policy question (should `ACCEPT` be reachable?) is a business/engineering-policy decision outside this audit's scope. | **HIGH** |
| `feature/vertical-slice` (branch, not a file) | **OBSOLETE** | Fact: fully merged into `main` (0 commits ahead, 20 behind); not referenced by name in any current documentation. Recommendation: safe to archive/delete per your team's normal branch-hygiene policy — it adds no value as a separate ref once fully absorbed into `main`. | `git log --oneline main..feature/vertical-slice` (0 results). | Delete or archive, at the business owner's discretion — no urgency, purely tidiness. | **LOW** |
| `.DS_Store`, `slice/.pytest_cache/`, `slice/__pycache__/`, `slice/tests/__pycache__/` | **CORRECT** | Fact: present as untracked, ignored files in the current working tree; `.gitignore` already covers all four patterns. No git-tracked instance of any of them exists anywhere in history. | `git status --short --ignored`, `git clean -ndx`. | None needed — flagged only to confirm the audit checked for this. | — |
| `slice/fixtures/sample-service/*`, `slice/fixtures/setup_fixture.sh` | **CORRECT (Fixture)** | Fact: still used by `pilot-ci.yml`; still exercises real, current analyzer behavior (its `services/widget-service/` naming is coincidental — it works because it has its own `package.json`, not because of any special-cased path). | Read the script and workflow together. | None. | — |
| `slice/reports/verify-cache-change-report.md` / `.audit.json` | **CORRECT (Historical)** | Fact: the original Stage 1/pre-Stage-2B demonstration output, `TOOL_VERSION 0.2.0-pilot` / policy `v4` — five tool versions and five policy versions behind current. This is expected and correct for a historical artifact; not a defect. | File contents; compare to current `TOOL_VERSION 0.7.0-pilot` / `...-v9`. | None — retain as-is. Optionally add one sentence to `slice/README.md`'s reference noting explicitly "reflects tool/policy versions from Stage 1, not current" to preempt confusion. | **LOW** |
| `slice/PILOT_FEEDBACK_TEMPLATE.md` | **CORRECT** | Already current (Run ID column added in the Artifact History milestone). | Direct read. | None. | — |
| `design/design8.md`, `design/design9.md` | **CORRECT** | No stale branch names, TODOs, or status claims found; these remain the frozen, non-status-bearing domain-contract documents they're intended to be. | Grepped for branch names, TODO/FIXME, prototype language — none found. | None (also explicitly out of scope to modify). | — |
| `slice/ARCHITECTURE_DISCOVERY_DESIGN.md`, `slice/ARTIFACT_HISTORY_DESIGN.md`, `slice/ROUTE_DISCOVERY_MULTILINE_DESIGN.md` | **CORRECT** | Each is a point-in-time design doc, correctly framed as "written before implementation of milestone X"; no current-status claims that have since gone stale. | Direct read. | None. | — |

---

## 2. `.gitignore` review

**Current contents** (verbatim):
```
.DS_Store
__pycache__/
*.pyc
.pytest_cache/
slice/reports/pilot-*.md
slice/reports/pilot-*.audit.json
artifacts/
slice/artifacts/
```

| Proposed addition | What would otherwise be committed | Is it actually supposed to be preserved? | Recommendation |
| --- | --- | --- | --- |
| `.venv/`, `venv/`, `env/` | A local Python virtual environment, if a contributor creates one inside the repo (common habit). Currently **not** ignored. | No — never intended to be committed; large, machine-specific, regenerable from nothing (there's no `requirements.txt`/`pyproject.toml` currently, so a venv here would just be `pytest`). | Add. No evidence one has ever been committed, but the project has no other defense against it. |
| `.vscode/`, `.idea/` | Personal editor/IDE settings and workspace state. Not currently ignored. | No — personal, machine-specific. | Add, standard practice; no evidence of harm yet, purely preventative. |
| `node_modules/` | Not currently ignored anywhere in this repo. `slice/fixtures/sample-service/` has a `package.json` but its `node_modules/` would only ever be created in a copy made by `setup_fixture.sh` in a temp directory *outside* this repo — so this is a **defensive**, not **reactive**, addition. | No — regenerable via `npm install`, and no target repository's `node_modules/` is ever checked out inside this repo (it's cloned to a separate path). | Add as a defensive measure; low urgency since no instance found in history. |
| `.coverage`, `htmlcov/` | Python coverage tool output. Not currently ignored. Not currently *generated* either — no coverage tooling is invoked anywhere in this project today. | N/A today. | Optional/low priority — add only if/when coverage tooling is actually introduced; adding it now is harmless but addresses a need that doesn't yet exist. |
| `*.env`, `.env` | Environment-variable files. Several historical reports (e.g. `regression-verification/README.md`) discuss supplying `JWT_SECRET`/`JWT_REFRESH_SECRET` as env vars when analyzing *target* repositories — but those are supplied to the target repo's own process, never written as a file inside *this* repo. | No — should never be committed if one ever appears. | Add as a standard defensive measure; no evidence of one ever existing here. |

**Not recommended:** no changes to the existing four base patterns or the two most recent additions (`pilot-*`, `artifacts/`/`slice/artifacts/`) — all four were verified against actual repository state (§1, "CORRECT" row) and remain accurate and necessary.

---

## 3. GitHub Actions workflow review

| Workflow | Claim in `PILOT.md` | Verified against workflow file | Result |
| --- | --- | --- | --- |
| Invocation (Actions tab → workflow → Run workflow) | ✓ matches `on.workflow_dispatch` in `run-analysis.yml` | ✓ | **CORRECT** |
| Required inputs (`target_repo`, `target_ref` required; `base_ref` optional, default `main`) | ✓ matches `inputs:` block exactly | ✓ | **CORRECT** |
| Public vs. private repo access (`TARGET_REPO_TOKEN`, read-only scopes) | ✓ matches `token: ${{ secrets.TARGET_REPO_TOKEN \|\| github.token }}` | ✓ | **CORRECT** |
| Permissions / read-only behavior | ✓ `permissions: contents: read`; target checkout `persist-credentials: false`; no write step anywhere in the job | ✓ | **CORRECT** |
| Artifact upload (three files, named by run ID, downloadable) | ✓ matches `actions/upload-artifact@v4` step with `name: run-${{ env.RUN_ID }}` | ✓ | **CORRECT** |
| Run/history behavior ("every run is kept, never overwritten") | ✓ matches `--artifacts-root`/`exist_ok=False` behavior in `artifact_history.py` | ✓ | **CORRECT** |
| Branch/default-branch assumption | Not documented | `base_ref` defaults to `"main"`; will fail cleanly but unexplained for a `master`-default repo | **See §1 row (MEDIUM)** |
| Failure behavior | Documented only as "a bug in the tool, not your repository" | The "no changes found" exit path isn't covered by that description, and the upload step's behavior in that case is untested | **See §1 row (MEDIUM)** |

`pilot-ci.yml`'s scope (analyzer's own tests + a self-contained fixture smoke test, never touching another team's repository) is accurately described by its own header comment and isn't referenced by `PILOT.md` at all (correctly, since it's an internal-only workflow) — **CORRECT**.

---

## 4. Historical artifact classification

| Location | Classification | Notes |
| --- | --- | --- |
| `slice/reports/verify-cache-change-report.{md,audit.json}` | **Historical** | Stage 1 demonstration output. Preserve as-is. |
| `slice/reports/vertical-slice-package.md` | **Historical**, banner needs a status update (§1) | Content about Stage 2B itself is accurate; only the top banner is stale. |
| `slice/reports/user-management-app-pilot/*` | **Historical** | Stage 2C findings; accurately framed throughout as past-tense. |
| `slice/reports/user-management-app-pilot/fixtures/*.patch` | **Fixture** | Actively reused by every architecture-discovery round's regression check through v9; not obsolete. |
| `slice/reports/adapt-architecture-discovery/ADAPT_ARCHITECTURE_DISCOVERY_report.md` + `held-out-results/` + `regression-verification/` (v5, unversioned) | **Historical** | Distinct content from later rounds — not a duplicate. Naming inconsistency only (§1). |
| `slice/reports/adapt-architecture-discovery/*_v6_*` through `*_v9_*` and their `held-out-v{6,7,8,9}/`, `regression-verification-v{6,7,8,9}/` | **Historical** | Each is the accurate record of its own round. |
| `slice/reports/adapt-architecture-discovery/NEXT_MILESTONE.md` | **Historical**, needs a superseded-by-v7 note (§1) | Real record of a real business decision point; do not delete. |
| `slice/reports/ARTIFACT_HISTORY_final_report.md` | **Current** | Describes the milestone most recently accepted onto `main`. |
| `slice/fixtures/sample-service/*`, `setup_fixture.sh` | **Fixture** | Actively used by `pilot-ci.yml`. |
| `slice/tests/*.py` | **Current** | All four files pass, all exercise present-day behavior, none reference retired code paths. |

**No item in this section is recommended for deletion.** Nothing was classified as **Obsolete** or **Duplicate** among the historical report content itself — the only redundancy-*shaped* findings (§1) are naming-convention inconsistencies (v5's unversioned directories), not actual duplicate content.

---

## 5. Product-position language (§7)

- `README.md`'s "not a finished product... this is a pilot" framing is accurate and doesn't need correction on positioning grounds — the factual error embedded in the same sentence (the `services/<name>/` claim) is the actual problem (§1).
- `slice/README.md`'s title and its line-19 leftover paragraph are the two places that read as if `ADAPT_ARCHITECTURE_DISCOVERY` is still "the current milestone" / "not merged" — both flagged in §1.
- `slice/reports/vertical-slice-package.md`'s banner reads as if the project paused after Stage 2B awaiting a decision that was made long ago — flagged in §1.
- No document was found describing the product as "an early prototype" or "a one-repository proof of concept" in the present tense — that framing only appears correctly, in the past tense, inside historical Stage 1/2C narrative.

No rewrite is proposed here, per instruction — these are flagged for a business decision on repositioning language, not applied.

---

## 6. Documentation-vs-code verification summary (§6)

| Claim | Where documented | Verified against | Result |
| --- | --- | --- | --- |
| Component discovery via `package.json` presence anywhere | `slice/PILOT.md` line 66 | `discovery.find_components()` | **Matches** |
| Route discovery, any receiver, formatting-independent | `slice/PILOT.md` line 66 | `discovery.find_route_registrations()`, `ROUTE_DISCOVERY_MULTILINE_DESIGN.md` | **Matches** |
| TypeScript (`.ts`/`.tsx`) support | Not explicitly stated in `PILOT.md` (implementation detail); stated correctly in `ARCHITECTURE_DISCOVERY_DESIGN.md`/v6 report | `discovery.SOURCE_EXTENSIONS` | **Matches** (no doc contradicts it) |
| CommonJS object-literal export shorthand | Not mentioned in `PILOT.md` (correctly an implementation detail); documented in v8 report and `discovery.py` docstrings | `discovery._object_literal_export_names()` | **Matches** |
| Multiline route support | `slice/PILOT.md` line 66 ("regardless of formatting") | `discovery.find_route_registrations()` / `ROUTE_METHOD_RE` + `_extract_balanced` | **Matches** |
| Artifact history / run IDs / immutability | `slice/PILOT.md` lines 25–32 | `artifact_history.py`, `slice/tests/test_artifact_history.py` | **Matches** |
| CI history kept separate, never fed into probability | `slice/README.md` §"Stage 2" | `fetch_ci_history()` usage in `analyze_change.py` (additive only) | **Matches** |
| Cross-service validation as its own evidence category | `slice/README.md` §"Stage 2B" | `CROSS_SERVICE_VALIDATION` handling in `build_validation_decision()` | **Matches** |
| Decision behavior: three possible outcomes including "proceed"/`ACCEPT` | `slice/PILOT.md` line 59 | `final_recommendation()` | **Disagreement — see §1 (HIGH)** |
| Repository-layout assumptions (`services/<name>/`) | `README.md` line 17 | `discovery.py` (no such assumption) | **Disagreement — see §1 (HIGH)** |

---

## 7. Verification

- **No implementation, design, policy, or CI files were changed.** The only file created by this task is `REPOSITORY_HYGIENE_AUDIT.md` itself.
- `git status --short` before and after this audit: clean, no changes outside the new report file.
- **Current `main` commit SHA:** `659aa48a01b58ef7fd4215ddfd8104b143ed5a5a`
- **Current baseline tags:** `architecture-discovery-v9-baseline`, `artifact-history-baseline`
- **Current test count:** **89 passing.** (Historical counts quoted in §1/§4 — 24, 42, 47, 57, 66, 74 — belong to specific past milestone reports and are correct only in that historical context; they are not the current count.)
- Nothing was committed or pushed. This report exists only in the working tree pending your review.

## Definition of done

This is the inventory. No file besides this one was touched; no product-position, policy, or deletion decisions were made on your behalf. The next decision — what to fix, what to leave as historical record, and how to reposition the top-level documentation — is yours to make.
