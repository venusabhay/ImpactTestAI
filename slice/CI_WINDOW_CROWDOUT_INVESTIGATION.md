# CI window crowd-out: investigation (no implementation)

**Scope:** investigation only, on `investigate/ci-window-crowd-out`
(branched from `main` @ `da3d6d8`, immediately after the 0.10.0 generic
workflow-discovery milestone). No code changed --
`git diff --stat main..investigate/ci-window-crowd-out -- slice/analyze_change.py`
is empty. `POLICY_VERSION`, risk scoring, discovery, and recommendation
behavior are untouched. This follows directly from
`slice/CI_WORKFLOW_DISCOVERY_INVESTIGATION.md` §3, which named this same
crowd-out mechanism as a real but separate, deferred problem.

## 1. The mechanism being measured

`fetch_ci_history()` calls `GET /repos/{repo}/actions/runs?per_page=100`
-- one repo-wide fetch, newest-first, capped at 100 runs, mixing every
workflow in the repository together. A repository-authored workflow can
have substantial real history and still contribute **zero** runs to that
window if enough *other* workflows in the same repo run more frequently.
0.10.0 fixed *which filenames* are accepted; it did nothing about *how
far back* the fetch reaches.

## 2. Method

For each candidate repository: fetch the real (`.github/workflows/`-
authored, non-`dynamic/`) workflow list; fetch the same repo-wide 100-run
call the analyzer itself makes and record which real workflow paths
appear in it and how many runs each contributes; for every real workflow
with **zero** runs in that window, fetch its own recent history via
`GET /actions/workflows/{id}/runs` to check whether it has real completed
runs that simply fell outside the window, and how old the most recent one
is relative to the window's date range.

Four real, high-workflow-volume repositories were measured this way
(`socketio/socket.io`, `fastify/fastify`, `sequelize/sequelize`,
`expressjs/express` -- chosen as the highest-workflow-count repos already
sampled in the 0.10.0 investigation). Measurement was interrupted twice by
the unauthenticated GitHub API's 60-requests/hour limit -- itself a
relevant data point, discussed in §5.

## 3. Findings per repository

| Repo | Real workflows | Total runs (all-time) | Window covers | Zero-in-window real workflows | Is the *primary* CI/test workflow crowded out? |
|---|---|---|---|---|---|
| `socketio/socket.io` | 15 | 750 | 17 days (`2026-08-11` to `2026-08-28`) | 4 (`ci.yml`, `publish.yml`, `ci-engine.io-parser.yml`, `ci-socket.io-component-emitter.yml`) | **Yes.** `ci.yml` (198 runs all-time -- the single largest real workflow in the repo) has 0 runs inside the window; its most recent run is 43 days older than the window's oldest entry. Crowded out by 10 per-package `ci-<package>.yml` workflows each contributing 12-13 runs to the same window. |
| `fastify/fastify` | 21 | 13,823 | **13 hours** (`2026-08-28T10:05` to `2026-08-28T22:55`) | 10 (website, package-manager-ci, lock-threads, coverage-nix/win [never run at all, 0 total], lint-ecosystem-order, citgm/citgm-package, validate-ecosystem-links, ci-deno) | **No.** Despite the window covering barely half a day at this repo's run volume, `ci.yml` still contributes 7 runs inside it. Everything crowded out is a secondary/auxiliary workflow (docs site, coverage-only jobs, a legacy alt-runtime variant, bots) -- not the workflow a service-level test-outcome question would target. |
| `sequelize/sequelize` | 10 | 10,367 | 8 days | 2 (`notify.yml` -- 4 runs all-time, release-channel notifications; `test-draft.yml` -- 2 runs all-time, draft-PR labeling) | **No.** `ci.yml` has 17 runs in-window. Both crowded-out workflows are trivial by name and run count, not test/CI workflows at all. |
| `expressjs/express` | 6 | 1,200 | 45 days | 2 (`iojs.yml` -- a legacy alt-runtime CI variant, 35 runs all-time; `labeler.yml` -- 1 run ever) | **No.** `ci.yml` has 27 runs in-window. |

**1 of 4 sampled repositories (25%) had its primary CI/test workflow
crowded out.** In the other 3, the window comfortably captures the
workflow that a service-level evidence question would actually care
about, even in `fastify`'s case where the window covers only ~13 hours of
wall-clock time at that repo's extreme run volume -- because a
frequently-changed primary workflow simply reappears often enough to
survive a short window; it's *low-frequency, non-primary* workflows that
get crowded out, and those are rarely what `fetch_ci_history()`'s
job-name-vs-service matching would have found relevant anyway.

## 4. A compounding finding in the one real crowd-out case

For `socketio/socket.io`, whether crowd-out is fixed doesn't obviously
answer whether evidence for the **root** `socket.io` package would
actually improve. `discovery.find_components()`/`component_for_path()`
supplies the `service` string `fetch_ci_history()` searches job names for
-- in a package.json-rooted monorepo like this one, that's the real npm
package name, e.g. `socket.io`, `socket.io-client`, `engine.io`.

A real job pulled from `ci.yml`'s own (crowded-out) run history is named
**`test-node (16)`** -- it does not mention `socket.io` (or any package
name) at all. The existing job-name-vs-service regex
(`\b{service}\b`, unchanged and out of scope here) would not match this
job even if its run were inside the window. By contrast, the per-package
`ci-<package>.yml` workflows -- which *are* well-represented in the
window -- follow a workflow-level naming convention keyed to the package
already (e.g. `ci-socket.io-client.yml`), so the packages most likely to
be the target of a real code change already have working, in-window
evidence today.

This means the one clear crowd-out case found is also the case with the
weakest payoff: fixing the window wouldn't, by itself, produce usable
root-package evidence here, because a second, independent gap (job names
that don't mention the service at all) sits behind it -- and that gap is
explicitly out of scope for this investigation and not something to
solve alongside a window-size fix.

## 5. Cost: is per-workflow fetching worth it?

The only way to see runs a repo-wide 100-run fetch pushes out is to fetch
each real workflow's own run history separately
(`GET /actions/workflows/{id}/runs`) -- one additional API call per real
workflow file, on every analysis run that requests CI history. Measured
directly against this investigation's own sample:

| Repo | Real workflow count | Extra calls needed (vs. today's 1) |
|---|---|---|
| `fastify/fastify` | 21 | up to 21x |
| `socketio/socket.io` | 15 | up to 15x |
| `sequelize/sequelize` | 10 | up to 10x |
| `expressjs/express` | 6 | up to 6x |

This investigation itself hit the unauthenticated GitHub API's
60-requests/hour ceiling **twice** while measuring only 4 repositories
(and again during the prior 0.10.0 milestone's real-world verification) --
CI rate-limit pressure is not a hypothetical concern here, it is a
directly observed, recurring operational fact in this exact project, on
exactly this API. Moving from 1 call to up to 21 calls per analysis for
CI-heavy repositories would make that ceiling bind far sooner and far
more often, for a benefit that -- per the sample above -- helps the
*primary* workflow in only 1 of 4 cases, and even there does not clearly
translate into better final evidence (§4). CI rate-limit mitigation is
already a separately deferred item; this fix would make that problem
materially worse before anyone works on it.

## 6. Decision gate

**Is crowd-out common and material enough to justify an implementation
milestone? No -- defer it.**

- **Not common for what matters:** the primary/relevant CI workflow was
  crowded out in 1 of 4 high-workflow-volume repositories sampled. In the
  other 3 -- including one whose window covers only 13 hours of
  wall-clock time -- the workflow that service-level evidence would
  actually target remained visible.
- **Uncertain payoff even in the positive case:** the one repository
  where crowd-out is real and severe (`socket.io`) also has a distinct,
  unrelated job-naming gap that would likely blunt or negate the benefit
  of fixing the window alone for the case that would matter most (the
  root package).
- **Real, already-observed cost:** implementing per-workflow fetching
  would multiply API calls per analysis by up to 21x on repositories like
  these, directly worsening the rate-limit ceiling this investigation
  itself hit twice while just measuring the problem.

**Recommendation:** defer, per the decision rule. If a future real pilot
run surfaces a concrete case where a decision-relevant service's own
primary workflow was genuinely invisible due to window crowd-out (not
just "this repo has many workflows," and not confounded by a job-naming
gap like `socket.io`'s), revisit with that specific evidence in hand
rather than building general per-workflow fetching speculatively now.

Other deferred items are unaffected and remain untouched: environment-
variable classification, indirect auth/`passport.ts` discovery, `ACCEPT`
policy, CI rate-limit mitigation, retries, broader risk-model changes.
