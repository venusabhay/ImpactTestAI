# CI workflow discovery: investigation (no implementation)

**Scope:** investigation only, per the engineering instruction on
`investigate/ci-workflow-discovery` (branched from `main` @ `140b668`).
`analyze_change.py` was not modified for this document -- confirmed via
`git diff --stat main..investigate/ci-workflow-discovery -- slice/analyze_change.py`
(empty). `POLICY_VERSION`, risk scoring, discovery, and recommendation
behavior are untouched.

## 1. Exactly how the analyzer currently selects CI history

`fetch_ci_history()` (`analyze_change.py:702`) does one repo-wide API call:

```
GET /repos/{github_repo}/actions/runs?per_page=100
```

This endpoint is **not** scoped to any single workflow -- it returns the
repository's most recent runs across *every* workflow GitHub knows about,
mixed together, newest first, capped at `per_page` (100 here, i.e. only
the 100 most recent runs of any kind).

The code then filters that list client-side (`analyze_change.py:740-743`):

```python
runs = [
    r for r in runs_data.get("workflow_runs", [])
    if r.get("path") == workflow_path and r.get("status") == "completed"
]
```

`workflow_path` defaults to `".github/workflows/ci.yml"` and has **no CLI
override** -- confirmed via `python3 analyze_change.py --help`, no
`--workflow-path` flag exists, and `fetch_ci_history()` is called at
exactly one site (`main()`, `analyze_change.py:1229`) with no argument
for it.

Only runs surviving that filter are ever looked at for job-level detail.
Everything downstream of this point -- the job-name-vs-service matching
(`analyze_change.py:758-770`), the failure/success/cancellation counting,
the `historical_signal` text -- is already generic and already correct;
it operates on whatever runs it's handed. **The defect is entirely in
which runs it's handed**, not in how it reasons about them once received.

## 2. Real-repo measurement

10 real, public repositories were queried directly against the same
`GET /actions/runs?per_page=100` endpoint the analyzer itself calls
(read-only `curl`/`urllib` calls made independently for this
investigation; `analyze_change.py` itself was not invoked against these
repos for this section). For each, every distinct `path` present in the
fetched runs was extracted, with a completed-run count per path.

| Repo | Completed runs (top 100) | Hardcoded `ci.yml` hit? | Real CI-relevant workflow(s) present |
|---|---|---|---|
| `saisilinus/node-express-mongoose-typescript-boilerplate` | 53 | **Miss** (0 matches) | `.github/workflows/node.js.yml` (16 runs) -- already known from the prior pilot round |
| `tt-a1i/archify` | 100 | Hit (75 matches) | `.github/workflows/ci.yml` |
| `developit/express-es6-rest-api` | 0 | N/A -- no runs at all | none -- genuinely no GitHub Actions history exists |
| `venusabhay/social-media-mini` | 24 | Hit (7 matches) | `.github/workflows/ci.yml`, alongside `codeql.yml` (16 runs, unrelated) |
| `venusabhay/user-management-app` | 0 | N/A -- no runs at all | none -- genuinely no GitHub Actions history exists |
| `expressjs/express` | 100 | Hit (27 matches) | `.github/workflows/ci.yml`, alongside `codeql.yml` (33), `legacy.yml` (25) |
| `fastify/fastify` | 100 | Hit (7 matches, small share) | `.github/workflows/ci.yml` present but crowded by 11 other workflows (labeler, md-lint, pull-request-title, etc.) |
| `nestjs/nest` | 100 | **Miss** (0 matches) | **none** -- confirmed via `/actions/workflows`: only CodeQL + Copilot/Dependabot bot workflows exist; no test/build workflow runs on GitHub Actions at all |
| `sequelize/sequelize` | 100 | Hit (18 matches) | `.github/workflows/ci.yml`, alongside `semgrep.yml` (24), `pr-title.yml` (23) |
| `socketio/socket.io` | 100 | **Miss** (0 matches in this window) | `.github/workflows/ci.yml` exists (confirmed via `/actions/workflows`) but produced **zero** runs in the most recent 100 -- crowded out by 10 higher-frequency **per-package** `ci-<package>.yml` workflows (e.g. `ci-socket.io-client.yml`, `ci-socket.io-adapter.yml`) |

**3 of 10 sampled repos (30%) had real, examined CI history that the
current hardcoded filter makes completely invisible** -- and they fail
for two distinct reasons, not one:

- **Filename mismatch** (`saisilinus`): the real workflow file is simply
  named something else (`node.js.yml`). The runs are present in the
  fetched page; the path filter throws them away.
- **Window crowd-out** (`socket.io`): the real workflow *is* named
  `ci.yml`, so a smarter filename guess wouldn't even help here -- it
  just runs far less often than ten sibling per-package CI workflows in
  the same repo, so none of its runs appear in the 100 most recent
  repo-wide runs at all. This is a distinct failure mode from filename
  guessing, worth naming separately for any future fix.

One repo (`nestjs/nest`) hit the hardcoded filter *and* has genuinely no
CI-via-Actions workflow -- correctly "no history exists," not a bug, but
it shows the hardcoded-miss signal alone can't distinguish "wrong
filename" from "no workflow at all" without a second check (see §4).

## 3. Is generic discovery feasible without repository-specific rules?

**Yes**, and the sample above points at a specific, minimal mechanism —
one that needs **no added API call** and **no filename list**:

Every run GitHub returns for a *user-authored* workflow file has a `path`
starting with `.github/workflows/`. Every run tied to a GitHub-managed
feature surfaced through the same endpoint (Dependabot updates, CodeQL's
managed default setup, Copilot's PR reviewer/agent, Pages deployments)
has a `path` starting with `dynamic/` instead — confirmed across
`saisilinus` (`dynamic/dependabot/dependabot-updates`), `nestjs/nest`
(`dynamic/github-code-quality/codeql`, `dynamic/copilot-swe-agent/copilot`,
etc.), `expressjs/express`, and `fastify/fastify`. This is a **GitHub
API-level convention, not a per-repository or per-language rule** — it
reflects whether the run came from a file actually committed to the
repo at all.

That means the existing repo-wide `/actions/runs` call already contains
everything needed: replacing the single hardcoded equality check
(`r.get("path") == ".github/workflows/ci.yml"`) with a generic
"real, user-authored workflow" check (`r.get("path", "").startswith(
".github/workflows/")`) — combined with the job-name-vs-service matching
that already exists and is already generic (`analyze_change.py:758-770`,
driven by the target's own name, not a filename) — would:

- Surface `saisilinus`'s `node.js.yml` runs with no new code path, since
  the job-name matching already searches by service name within
  whatever runs it's given.
- Surface each of `socket.io`'s per-package `ci-<package>.yml` runs the
  same way, without ever needing to know any of those filenames in
  advance — the existing service-name job matching (e.g. a service named
  `socket.io-client` naturally matches a job in `ci-socket.io-client.yml`'s
  run) does the discrimination generically.
- Correctly continue reporting `nestjs/nest` as no-usable-history, since
  none of its real workflow runs (there are none) would produce a
  service-name job match either way.
- Not require a workflow-name allowlist, a per-language default, or any
  repository-specific configuration.

This does **not** solve `socket.io`'s window crowd-out case if a
low-frequency real workflow's runs fall outside the 100 most recent
*repo-wide* runs -- that would need switching to the per-workflow
`/actions/workflows/{id}/runs` endpoint (one additional API call per
discovered workflow file), which is a real, separate cost/complexity
tradeoff: cheap for repos with 1-3 real workflows, expensive for repos
like `socket.io` (11 real workflow files) or `fastify` (12), and directly
adjacent to the already-known, already-deferred CI rate-limit concern.
**Recommendation: solve the filename-mismatch case first** (zero added
API cost, fixes 1 of the 2 observed failure modes, e.g. `saisilinus`);
treat the window-crowd-out case as a second, separate, smaller follow-up
if it turns out to matter in practice, not bundled into the same change.

## 4. Preserving the four required states

| State | How it's distinguished today | After the proposed filter change |
|---|---|---|
| No workflow/history exists | `runs_examined == 0` after filtering; `historical_signal` reads "no CI job matching..." | Same signal text still fires when zero real (`.github/workflows/`) runs exist at all -- confirmed against `developit/...` and `venusabhay/user-management-app` (0 runs of any kind) and would also correctly fire for `nestjs/nest` (0 *real* runs, even though 100 *synthetic* ones exist) |
| Workflow exists but no relevant runs | Same `historical_signal` branch as above -- **already ambiguous with the row above**, since `runs_examined` counts runs but the message doesn't say how many | Unaffected by this change either way; a pre-existing, narrower gap worth noting for the eventual implementation but not required to answer this decision gate |
| Workflow exists but cannot be retrieved | `except _CI_HISTORY_TRANSIENT_ERRORS` -> `available: False`, real `error` string (fixed in the 0.9.0 milestone) | Unaffected -- this is a network-layer concern, orthogonal to which `path` values are accepted |
| Workflow exists and usable history was found | `service_job_results` non-empty -> failure/success counts and `historical_signal` computed normally | Unaffected in shape; would now actually populate for `saisilinus`- and `socket.io`-style repos instead of silently staying empty |

The one genuine gap found in this pass (row 2 above) is narrow, already
present in the *current* code independent of the filename question, and
not required to answer the decision gate below -- flagged for whoever
picks up the implementation, not proposed as part of it.

## 5. Decision gate

**Is workflow discovery sufficiently common and sufficiently reliable to
justify an implementation milestone? Yes.**

- **Common:** 3 of 10 sampled real repos (30%) had real, retrievable CI
  history that today's hardcoded filename makes completely invisible --
  not a hypothetical, and consistent with the one repo already found
  affected in the prior pilot round (`saisilinus`, discovered
  independently there).
- **Reliable:** the filename-mismatch half of the problem (2 of the 3:
  `saisilinus`, and structurally the same shape as any repo using
  `node.js.yml`/`test.yml`/`build.yml`/etc.) has a fix that is generic
  (keyed off a GitHub API-level convention, not a filename list or
  per-repo rule), reuses all existing job-name-matching logic unchanged,
  and costs zero additional API calls.
- **Scoped correctly:** the harder crowd-out half of the problem
  (`socket.io`) is real but separable, has a clear but costlier fix
  (per-workflow run fetching), and should not block or be bundled with
  the cheaper, more common fix.

**Recommendation:** proceed with an implementation milestone scoped to
*only* the filename-generalization fix in §3 (drop the hardcoded
single-path equality check in favor of the generic
`.github/workflows/` prefix check) -- explicitly not the window
crowd-out fix, not workflow-name allow-listing, and not any of the
other items already deferred from the 0.9.0 milestone (environment-variable
classification, `passport.ts`/indirect auth discovery, `ACCEPT` policy,
CI rate-limit mitigation, retries, broader risk-model changes -- all
remain out of scope here too).
