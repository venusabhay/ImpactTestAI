# Vertical Slice — First Implementation Milestone

> **Just want to run this against your own repository?** Go to [`PILOT.md`](PILOT.md) — a short, non-technical guide. Everything below is engineering/history detail, not required reading for pilot users.

**Current status: `ADAPT_ARCHITECTURE_DISCOVERY` v7 implemented and evaluated on `feature/adapt-architecture-discovery` (not merged to `main`).** This round fixed exactly the two gaps the v6 held-out round found — comment-blind scanning (a code-shaped example inside a comment was matched as a real route) and class-based controller handlers not connecting to their routes (`controller.methodName` property-access references) — via a comment-stripping pass (`discovery.strip_comments()`) and root-identifier export resolution (`discovery._resolve_arg_to_export()`). Both fixes were re-verified end-to-end against the exact repository that found them. A fresh held-out round against two genuinely unseen repositories found real positive generalization (`node-express-boilerplate`: two new routes correctly and precisely identified, correct discrimination between a meaningful and a trivial change) and one correctly-safe out-of-scope refusal (`nestjs-realworld-example-app`'s decorator-based routing) — but also surfaced one new, general discovery gap: CommonJS `module.exports = { name1, name2, ... }` object-literal export shorthand is not recognized. **Recommendation: `NEEDS_MORE_WORK`** — full v7 report: [`reports/adapt-architecture-discovery/ADAPT_ARCHITECTURE_DISCOVERY_v7_final_report.md`](reports/adapt-architecture-discovery/ADAPT_ARCHITECTURE_DISCOVERY_v7_final_report.md) (prior rounds: [v6](reports/adapt-architecture-discovery/ADAPT_ARCHITECTURE_DISCOVERY_v6_final_report.md), [v5](reports/adapt-architecture-discovery/ADAPT_ARCHITECTURE_DISCOVERY_report.md)).

This is the first real implementation of the design8/design9 decision chain, scoped exactly as directed.

**Stage 1 (frozen):** one repository, no production/incident/organizational access, one real change, taken all the way through to a validated, explainable decision.

**Stage 2 (accepted):** the same chain, with exactly one real operational data source added — this repository's actual GitHub Actions run history — kept strictly as additive evidence, never as an input to probability or the recommendation algorithm. See "Stage 2" below.

**Stage 2B (accepted):** closes the specific capability gap Stage 1 identified and Stage 2 declined to paper over — a real cross-service integration test that actually exercises the changed `/verify` behavior the way `post-service`/`user-service` depend on it. Result: **it found a real regression**, verified to be genuinely caused by the change (not pre-existing, not a test artifact, reproducible 3/3 runs). See "Stage 2B" below and the acceptance banner in the package doc.

**Stage 2C — cross-repository pilot (accepted):** ran the exact Stage 2B implementation, unmodified, against `user-management-app` — a repository with no `services/<name>/` layout, `express.Router()` instead of `app.METHOD()`, in-process auth middleware, and no CI. Three real changes were tested; impact/evidence/validation were empty in all three, and a genuine cross-component contract break scored identically to a trivial UI tweak. Full findings, ground-truth verification, and per-dimension usefulness scores: [`reports/user-management-app-pilot/user-management-app-pilot-report.md`](reports/user-management-app-pilot/user-management-app-pilot-report.md). The three test changes are preserved as reusable fixtures: [`reports/user-management-app-pilot/fixtures/`](reports/user-management-app-pilot/fixtures/), with acceptance criteria in [`RERUN_ACCEPTANCE_CRITERIA.md`](reports/user-management-app-pilot/RERUN_ACCEPTANCE_CRITERIA.md). Recommendation was `ADAPT_ARCHITECTURE_DISCOVERY`.

**`ADAPT_ARCHITECTURE_DISCOVERY` (evaluated; current milestone; on `feature/adapt-architecture-discovery`, not merged):** replaced the hardcoded assumptions with evidence-based discovery (`slice/discovery.py`) — components from `package.json` presence anywhere, routes from any `receiver.method(...)` call, and a new middleware/dependency-discovery capability. All three `user-management-app` fixtures now pass their recorded acceptance criteria (re-run unchanged, byte-identical fixtures), and the `social-media-mini` security regression still reproduces identically. Held-out testing against `ai-agents` (a real 127-commit TypeScript monorepo) and `langgraph-demo` (a real Python CLI app) — neither used during development — found a real, previously-undisclosed gap: `.ts`/`.tsx` files are never scanned. Both held-out repositories otherwise failed safely and honestly (no fabrication, no crash), but produced no positive evidence of in-scope generalization, since both changes fell outside scope. Full report: [`reports/adapt-architecture-discovery/ADAPT_ARCHITECTURE_DISCOVERY_report.md`](reports/adapt-architecture-discovery/ADAPT_ARCHITECTURE_DISCOVERY_report.md). **Recommendation: `NEEDS_MORE_WORK`** — extend scanning to TypeScript, then repeat the held-out procedure against a fresh, in-scope, unseen repository.

```
Repository / PR
      ↓
Understand the change
      ↓
Determine potential impact
      ↓
Assess risk
      ↓
Determine appropriate validation
      ↓
Run one real validation
      ↓
Record the outcome
      ↓
Produce an explainable decision
```

## What's here

- [`analyze_change.py`](analyze_change.py) — the analyzer. Given a git repository and a ref to diff against, it produces a `Change`, `ImpactAssessment`, `RiskAssessment`, `ValidationDecision`, executes the recommended validation for real, records the `Outcome`, and renders a business-facing report plus a JSON audit record.
- [`reports/verify-cache-change-report.md`](reports/verify-cache-change-report.md) — the actual output for the demonstration change (see below).
- [`reports/verify-cache-change-report.audit.json`](reports/verify-cache-change-report.audit.json) — the structured record backing that report.
- [`reports/vertical-slice-package.md`](reports/vertical-slice-package.md) — the business-readable package (evidence available vs. missing, limitations, next-value opportunities) requested alongside the report.

## The demonstration change

Target repository: [social-media-mini](https://github.com/venusabhay/social-media-mini), cloned locally to `/Users/abhay/git-venusabhay/social-media-mini` (the canonical local location for this repo) — nothing was pushed back to it. A real, plausible code change was made to `services/auth-service/server.js`: the `/verify` endpoint (called by `post-service` and `user-service` on every authenticated request) was given a 5-second in-memory cache to reduce database load. This is exactly the kind of change the design was built to reason about: small, and touching a structurally central, security-adjacent path.

## How to reproduce (engineer, local CLI)

For running the analyzer yourself rather than through the pilot workflow (see `PILOT.md` for that):

```bash
python3 analyze_change.py <path-to-repo> \
  --against HEAD \
  --github-repo <owner/repo>    # optional, Stage 2: adds real CI run history
  --npm-install                 # optional: run `npm install` before validation (needed on a fresh checkout)
  --node-bin <directory>        # optional: only needed if the default `node` on PATH is broken/missing
  --out reports/some-report.md
```

Run `python3 analyze_change.py --version` to see the exact tool and policy version. Unit tests live in `tests/` (`python3 -m pytest tests/`); the CI fixture used to smoke-test the whole pipeline is in `fixtures/` (`bash fixtures/setup_fixture.sh`).

The tool only reads the target repository (and, with `--github-repo`, that repository's GitHub Actions run history) and runs its own existing `npm test` — it never modifies, commits, or pushes anything anywhere.

## Stage 2 — adding one operational data source (CI/test-run history)

Stage 1 could only ever say "the repository looks like this." It had no way to answer *"has this part of the system historically been unstable?"* Stage 2 adds exactly one operational data source to answer that — this repository's real GitHub Actions run history, pulled from the public REST API (no auth needed, no deployment required) — and nothing else. No production telemetry, no incident system, no second data source.

`fetch_ci_history()` fetches every completed run of the repository's `CI` workflow, fetches job-level detail for each, and matches jobs by name to the service under review (preferring a job whose name signals it's actually a test job, e.g. `Test Microservices (auth-service)`, over one that merely mentions the service, e.g. a Docker build job). It reports counts of confirmed failures, cancellations (caused by an unrelated sibling job — explicitly not counted as a failure), and successes, over an explicit time window.

**It is deliberately not wired into `probability`, `risk_level`, or the recommendation algorithm.** This was the one hard boundary set for Stage 2: a CI failure count must never become a fabricated "probability of failure," any more than a diff risk-indicator count should (the exact mistake Stage 1 caught and fixed in itself). CI history is additive evidence surfaced to a human reader in its own report section (`## HISTORICAL EVIDENCE (CI)`) and in the audit JSON (`ci_history`), not a new input to the math.

**Result for the demonstration change:** across the 7 real `CI` workflow runs in this repository's history, the `Test Microservices (auth-service)` job has **0 confirmed failures** (2 runs show it cancelled due to an unrelated job failing elsewhere in the same run — not counted). The recommendation for this change did **not** change — it remains `REQUIRE_ADDITIONAL_VALIDATION`, because the reason for that recommendation (no test exercises the new caching code; high structural exposure) is independent of whether this service has historically been stable. That is reported as a valid, expected result, not a shortcoming of the experiment.

### Answering the mandate's three questions

1. **What did CI history add that repository-only analysis could not know?** A concrete answer to "has this area broken before?" — previously an explicit unknown, now an explicit, evidenced answer ("no confirmed failures in the examined window") rather than a gap in the report.
2. **Did it materially improve the decision for this change?** No — the decision was already correctly `REQUIRE_ADDITIONAL_VALIDATION` for reasons CI history doesn't touch (the test-coverage gap and structural exposure). A clean CI history is reassuring context, not grounds to relax that recommendation, and the tool doesn't let it.
3. **Is CI history worth retaining as part of the product, or should it stay optional?** Worth retaining as a standard evidence source — it's cheap (same repo, no new system, ~8 API calls, no auth), and it's the only source so far that can distinguish "we have no data" from "we checked and it's been stable." Whether it should ever influence risk_level/probability, rather than staying purely descriptive, is a real question — but not one this stage's evidence answers, and not one to decide before a change exists where CI history *does* show real historical failures for the changed area.

## Stage 2B — closing the cross-service validation gap

Every prior stage's report said the same thing: *"a cross-service integration test that actually calls the live, changed endpoint from post-service, user-service would directly validate the structural risk identified above, but no such test exists in this repository."* Stage 2B's mandate was explicit: don't just make the report say more tests passed — answer whether the vertical slice can identify and execute a validation that actually exercises the changed `/verify` behavior across the services that depend on it.

`services/auth-service/verify-cross-service.integration.test.js` (added to the local clone at `/Users/abhay/git-venusabhay/social-media-mini`; not pushed to GitHub) does exactly that:

* It spawns the real, **unmodified** `server.js` as a live child process, connected to a real (ephemeral, in-memory) MongoDB — not imported in-process, not mocked.
* It drives that live process over real HTTP using `axios`, with the exact same call shape `post-service`/`user-service`'s `protect` middleware uses: `axios.post('${AUTH_SERVICE_URL}/verify', { token })`.
* Its second test targets the specific risk the platform's own `RiskAssessment` flagged for this change (`introduces or touches caching (statefulness / staleness risk)`): it registers a user, authenticates, primes the verification cache, **deletes the user directly from the database**, then immediately re-verifies the same token within the 5-second cache window — exactly what would happen if a real client made two requests in quick succession while an account was being deactivated.

**Result: the test failed.** The real, running service returned `200 OK` with a cached, stale user object for a token belonging to a user that no longer existed — a genuine authorization-bypass regression introduced by the caching change, invisible to every test that existed before this one (the existing suite never imports `server.js`, and no test previously touched the cache at all).

`analyze_change.py` was extended (not reopening design8/design9) to recognize this kind of test generically — `test_file_is_real_cross_service()` detects a test file that both makes real `axios` calls and spawns a child process, as distinct from an in-process/mocked test — and to select it as validation rather than reporting it as an unavailable capability. When it ran and failed, the pipeline's existing `any_failed` rule in `final_recommendation()` did the rest, unchanged: the decision became **`ESCALATE`**, with the exact regression message surfaced in the report's `VALIDATION RESULT` section.

**This is the strongest result the vertical slice has produced so far:** the platform didn't just hedge with "require more validation" — when the specific validation it said was missing was actually built, it caught a real defect the existing (weak) test suite structurally could not have found. Bumped `POLICY_VERSION` to `repo-plus-ci-plus-cross-service-v4` to reflect the new evidence category and validation-selection rule; probability is still not estimated, per v2/v3.

The application bug itself (the stale-cache authorization) was deliberately left unfixed — fixing it would remove the very evidence Stage 2B was built to demonstrate the platform can produce. The correct next action, per the report's own `ESCALATE` decision, is a human engineering decision (e.g. invalidate the cache entry on user deletion, or check a `deletedAt`/`active` flag on every verify regardless of cache), not something this tool does automatically.

## Deliberate simplifications vs. the frozen design

Per instruction, the architecture (design8.md / design9.md) was not reopened. Where it leaves an implementation choice open, the smallest reasonable choice was made here, and is listed explicitly rather than silently substituted:

| Design8/9 concept | What this slice actually does |
| --- | --- |
| Knowledge Graph, Evidence index, decision store | None of these exist. Every object is a plain in-memory structure for the duration of one run, serialized to a JSON audit file. There is no persistence across runs, no multi-hop graph traversal, and no historical corpus. |
| `Claim` with a versioned aggregation function | Not implemented. Each piece of evidence is surfaced directly in the report; confidence is a qualitative bucket (HIGH/MEDIUM/LOW) assigned by an explicit rule in `analyze_change.py`, never a numeric score presented as precise. |
| `RiskAssessment.probability` / `business_impact` as calibrated values | Qualitative buckets from explicit, inspectable rules (structural fan-in, sensitive-path-name match, newly-introduced-state patterns in the diff). Not calibrated against historical outcomes — there is no history yet. |
| `DecisionContext` | Approximated by recording the repo path, git ref/HEAD, and generation timestamp in the audit JSON. Sufficient to say what a decision was based on; not a general reproducibility service. |
| `RiskPolicy` | A single hardcoded threshold function (`final_recommendation()`), not a configurable, versioned object. There is exactly one policy and one organization in this slice. |
| `Override` | Not implemented — there is no running system to override yet; a human reads the report and decides. |
| `LearningSignal` / Continuous Learning | Not implemented — this slice produces one decision, it does not yet learn from outcomes across changes. |

None of these are architectural contradictions — they are exactly the kind of implementation-scoping decisions design8 §18 anticipated ("rules today" as the first point on the evolution path) and design9 explicitly deferred until there's a real slice to learn from.

## What this slice actually found

The most significant finding wasn't about the demonstration change's caching logic — it was that **none of the three backend services' test files import their own `server.js`**; each hand-duplicates its own route logic for testing. The analyzer detected this generically (it checks whether the test file covering a changed route imports the changed module) and used it to downgrade confidence and drive the final recommendation to `REQUIRE_ADDITIONAL_VALIDATION` even though the existing tests passed. See [vertical-slice-package.md](reports/vertical-slice-package.md) for the full writeup.

## Relationship to the rest of the repository

- [`../design/business-vision.md`](../design/business-vision.md) — the business framing this slice is meant to provide first evidence for.
- [`../design/design8.md`](../design/design8.md), [`../design/design9.md`](../design/design9.md) — the frozen domain contracts and architecture this slice implements a deliberately narrow slice of.
