# Product Validation / Pilot Acceptance Specification

This is the product contract for ImpactTestAI: what it promises, what
it explicitly does not, what evidence justifies each outcome it can
report, and how to measure whether a pilot round actually found it
useful. It synthesizes what six independent investigations
(`0.8`–`0.10` implementation milestones plus the CI-window-crowdout,
environment-failure-classification, and indirect-auth-discovery
investigations) established about where the current implementation is
trustworthy and where it is deliberately conservative instead.

**This document defines acceptance criteria. It does not propose new
implementation work.** Where the current implementation already meets a
criterion below, that is stated directly. Where it does not, that is
named as a gap — not silently, but also not as an instruction to build
something. Closing a gap is a separate, future engineering decision.

All terminology and behavior described below was verified directly
against `slice/analyze_change.py` and `slice/discovery.py` on `main`
@ `e57cf53` while writing this document — nothing here is aspirational
or inferred from documentation alone.

## Terminology note

Two different vocabularies exist in the tool's output and are easy to
conflate:

- **Validation-level outcomes** (`outcomes[i]["result"]`): `PASSED`,
  `FAILED`, `INCONCLUSIVE`. These describe one executed command (e.g.
  one `npm test` run in one component).
- **Top-level decisions** (`final_recommendation()`'s return value):
  `ACCEPT`, `REQUIRE_ADDITIONAL_VALIDATION`, `ESCALATE`. This is what
  the report's `## DECISION` section shows, and it is a function of
  *all* validation outcomes plus the risk assessment together, not a
  restatement of any single outcome.

The rest of this document uses "PASS" (as the surrounding product
conversation has) to mean **`ACCEPT`** — the top-level "proceed, no
further action needed" decision — and is explicit whenever it means the
validation-level `PASSED` outcome instead.

---

## 1. What ImpactTestAI promises

**Impact discovery.** Given a git diff, it identifies:
- **Direct impact**: routes/endpoints defined in a changed file, via any
  `receiver.method(path, ...)` call (any receiver name — `app`,
  `router`, `fastify`, a custom instance — not just `app.METHOD()`).
- **Middleware-dependency impact**: routes registered *elsewhere* that
  use one of the changed file's exports as a middleware/handler
  argument — a one-hop, export-to-usage relationship (see §2 for its
  precise limits).
- **Transitive/cross-service impact**: other components in the same
  repository whose code imports the changed file or calls out to the
  changed component, discovered via real import/require evidence, not
  assumed proximity.
- **Component boundaries** from `package.json` presence anywhere in the
  tree (not a fixed `services/<name>/` layout assumption).

**Validation.** It executes the **actual, pre-existing** `npm test`
script of every component discovered as affected — it does not write,
generate, or synthesize new tests, and it does not modify the target
repository in any way. If a real cross-service integration test already
exists and covers the change, that is identified and weighted as the
strongest available evidence. Optionally, with `--github-repo`, it
layers in the repository's real GitHub Actions run history as
*additional*, clearly-separated evidence — never as an input to risk or
probability.

**What each outcome means today:**

| Outcome | Meaning |
|---|---|
| `ACCEPT` | Selected validation passed; risk and confidence are both within this policy's acceptable bounds. **Currently unreachable — see §3.** |
| `REQUIRE_ADDITIONAL_VALIDATION` | Available evidence isn't strong enough to clear the change on its own (risk is high without direct coverage, or overall confidence is low) — proceed only after a human/additional check. |
| `ESCALATE` | Something failed, could not be completed, or produced no usable evidence at all. Do not proceed without a human. |
| `PASSED` / `FAILED` / `INCONCLUSIVE` (validation-level) | One executed command's real, unmodified result — a genuine pass, a genuine non-zero exit, or "could not produce a real result" (timeout, install failure, missing test infrastructure), respectively. |

Every report also states its own `probability: UNKNOWN` explicitly
(§2) and lists concrete `IMPORTANT UNKNOWNS` for anything it could not
determine — the tool is built to disclose the edges of its own
evidence, not paper over them.

## 2. What ImpactTestAI explicitly does not promise

- **No complete call-graph analysis.** Middleware-dependency discovery
  is exactly **one hop**: changed file → direct importer → that
  importer's own route registration. A controller that internally calls
  a service or validation layer does not propagate impact to that
  service/validation file (demonstrated directly in the
  indirect-auth-discovery investigation, Case 2 — kept on branch
  `investigate/indirect-auth-discovery`).
- **No universal framework understanding.** Route discovery recognizes
  exactly one calling convention: `receiver.method(path, ...)`. A
  repository using decorator-based routing (NestJS's `@Controller()`/
  `@Get()`/`@UseGuards()`) has zero discoverable routes, disclosed
  honestly, not guessed at (same investigation, Case 3). Side-effect-based
  registration (Passport's `passport.use(new Strategy(...))`, and any
  call-expression used as a middleware argument, e.g.
  `passport.authenticate('facebook')`) is not followed, by design —
  extending it was investigated and found unsafe to do generically
  (same investigation, §4).
- **No guarantee that missing CI history means no CI exists.** A repo-wide
  100-most-recent-runs fetch can miss a real, active workflow's runs if
  sibling workflows in the same repository run more frequently —
  demonstrated on `socketio/socket.io` (investigation record kept on its
  own branch, `investigate/ci-window-crowd-out`, per the repository's
  organization rule that investigation evidence stays separate from
  `main` until/unless it leads to an implementation). `CI history:
  UNKNOWN / insufficient evidence` never means "confirmed absent."
- **No automatic diagnosis of ambiguous environment failures.** A
  `FAILED` validation result is reported with its raw evidence and an
  explicit `classification: Unknown / insufficient evidence -- requires
  human triage` — the tool does not attempt to distinguish "this is
  really an environment problem" from "this is a real defect" beyond
  the one safe, structural signal available (a test *suite* that fails
  to even load, vs. an individual test that fails) — and even that
  narrower signal is not implemented today; see the
  environment-failure-classification investigation for why a broader
  version was found unsafe.
- **No pretending that insufficient evidence is a pass.** Zero
  discovered impact, no CI history, no test coverage, or a validation
  that could not run all surface as explicit unknowns or `ESCALATE` —
  never silently treated as "nothing to worry about."
- **No line/symbol-level attribution.** Export discovery operates at
  whole-file granularity: if any line in a changed file was touched,
  every export of that file is treated as equally implicated for
  middleware-matching purposes, even exports whose own code didn't
  change. This is a real, demonstrated source of over-broad (not just
  under-broad) impact claims — see indirect-auth-discovery Case 4b, a
  live, non-hypothetical false positive (a 754-line OAuth-only refactor
  causing 15 unrelated, unchanged routes to be listed as impacted).
- **No repository-specific behavior anywhere.** Every mechanism in
  `discovery.py` and `analyze_change.py` is checked, repeatedly across
  every milestone in this project, to contain zero references to any
  specific repository, filename, variable name, or route path. This is
  a deliberate constraint, not an oversight — it is also *why* several
  investigated improvements were deferred rather than built (CI
  filename discovery was fixed generically; workflow-crowd-out and
  indirect-auth fixes were not, because no generic mechanism was found).
- **No retries, and no second attempt at a flaky result.** A timeout or
  a single flaky test failure is reported once, honestly, as what
  happened on that one real execution — not smoothed over by re-running
  until a cleaner result appears.

## 3. What evidence is sufficient for each outcome

### `ACCEPT` ("PASS")

Per `final_recommendation()`, `ACCEPT` requires, in order: no `FAILED`
outcome, no `INCONCLUSIVE` outcome, at least one validation actually
ran, risk is not `HIGH`/`CRITICAL` without direct test coverage, **and**
overall confidence is not `LOW`.

**This last condition is never satisfied today.** `probability_confidence`
is hardcoded to `"LOW"` in every single call to `build_risk_assessment()`
(`analyze_change.py`, unconditional assignment, no branch) because this
policy version deliberately declines to estimate failure probability at
all in repo-only mode (no historical outcome data exists to calibrate
one against). Overall confidence is computed as the *weakest* of three
dimensions (`min(confidences, ...)`), so it is always exactly `LOW`,
regardless of how strong impact/evidence confidence are. **`ACCEPT` is
therefore structurally unreachable under the current policy —
confirmed both by direct code reading and by the fact that zero
`ACCEPT` decisions appear anywhere in this project's full corpus of
generated reports to date.** This is a deliberate, disclosed
conservative design choice (documented previously in
`docs/decisions/REPOSITORY_HYGIENE_AUDIT.md` §1, and reconfirmed here,
unchanged, as current fact) — not a bug, and not something this
document proposes to change. Whether `ACCEPT` should ever be reachable
under some future policy is a product/policy decision, explicitly
out of scope here (per the indirect-auth and environment-failure
investigations' own instruction not to touch `ACCEPT` semantics).

### `REQUIRE_ADDITIONAL_VALIDATION`

Sufficient evidence: every selected validation actually ran and none
`FAILED`/was `INCONCLUSIVE`, **and** either (a) risk is `HIGH`/`CRITICAL`
and no validation directly exercises the changed code path, or (b)
overall confidence is `LOW` (which, per above, is always). In today's
policy this is therefore the outcome for **every clean, fully-passing
run** — a deliberate floor, not a defect: a passing test suite is real,
useful evidence, but this policy does not treat it as sufficient on its
own to certify a change with no historical failure-rate data behind it.

### `ESCALATE`

Sufficient evidence, any one of: at least one validation `FAILED`; at
least one validation was `INCONCLUSIVE` (timeout, install failure, or
any other infrastructure condition); or no validation ran at all
(nothing selected, or nothing to select). This is the strict, ordered
first check in `final_recommendation()` — a single failure or
inconclusive result overrides everything else, including a low risk
level.

### `INCONCLUSIVE` (validation-level, evidence/infrastructure condition)

Fires, with a distinct disclosed `classification` string per cause, on:
a validation command exceeding `--validation-timeout-seconds` (default
180s); `npm install` exceeding its own timeout (300s) or exiting
non-zero; and (as a related, evidence-layer condition, not the same
field but the same philosophy) CI-history retrieval failing due to a
transient network/HTTP error, which produces `available: False` /
`UNKNOWN / insufficient evidence` rather than a validation outcome.
**In every case, this always results in `ESCALATE`** — an
`INCONCLUSIVE`/`UNKNOWN` result can never be quietly treated as a pass,
confirmed by dedicated regression tests
(`test_timeout_outcome_never_reaches_accept_or_require_additional_validation`,
`test_install_timeout_outcome_still_escalates`) that remain green.

## 4. How we measure usefulness

Anecdote-driven pilot rounds (five real cases in the 2026-08-28 round,
plus the individual milestone demonstrations before it) established
*that* the tool can be useful. Going forward, a pilot round should be
scored — per real case run — against these six criteria, each with a
concrete, checkable answer, not a vibe:

| # | Criterion | How to check it | Evidence this project already has |
|---|---|---|---|
| 1 | **Did it identify the affected component?** | Compare the report's `## POTENTIAL IMPACT` list against an independently-established ground truth for the real change (what a human reading the diff and the repo structure would say is actually affected) | Yes for direct/middleware-dependency hits (e.g. `auth.controller.ts` → 8 routes); no for the documented one-hop and convention limits (§2) |
| 2 | **Did validation actually exercise the relevant behavior?** | Check whether the selected test suite imports/calls the changed code path, not merely shares a directory with it — the report already surfaces this itself (`does NOT import or require ... re-implements its own routes`) | The tool already self-reports this distinction; it was the single most significant finding of the original Stage 1 vertical-slice demonstration |
| 3 | **Did it avoid claiming evidence it didn't have?** | Check that every `probability`, CI-history, and impact claim is either backed by a cited file/line/run or explicitly marked `UNKNOWN`/`insufficient evidence` | Yes, structurally — verified repeatedly across every milestone (`probability: UNKNOWN` always, CI failures always `UNKNOWN` never fabricated `0 failures`, confirmed by dedicated tests) |
| 4 | **Did it surface a genuine regression?** | Was there a real, independently-verifiable defect in the diff, and did the tool's validation result reflect it? | Yes — `social-media-mini`'s `/verify` caching regression, independently reproduced 3/3 on the changed code, 0/3 on the original |
| 5 | **Did it unnecessarily escalate?** | For a change with no real defect and adequate real test coverage, did the tool still `ESCALATE`/`REQUIRE_ADDITIONAL_VALIDATION` for a reason a human would consider excessive? | Documented, honestly: a one-character comment fix generated `REQUIRE_ADDITIONAL_VALIDATION` after its only check passed — flagged in the 2026-08-28 findings report as a real calibration concern, not dismissed |
| 6 | **Could a human reviewer understand why it reached the recommendation?** | Read `## WHY` and `## DECISION` without reading the source code — is the reasoning traceable to cited evidence? | Yes in every case examined across this project; this is the property most consistently validated, because every investigation in this project was itself only possible by reading the tool's own disclosed evidence |

**Recommended pilot-scoring mechanism:** for every real case run during
a pilot round, fill in this six-row table using
[`pilot/PILOT_FEEDBACK_TEMPLATE.md`](../pilot/PILOT_FEEDBACK_TEMPLATE.md)'s
existing structure (it already asks 1–6 in prose form) plus this
document's explicit ground-truth-comparison step for criteria 1, 4, and
5 specifically — those three require an independent human judgment
call the tool's own output cannot self-certify. Aggregate across a
round the same way `PILOT_FINDINGS_REPORT.md` already does (a
rollup table across cases, categorized findings, no claim of
statistical significance from a small sample) — this is not a new
process, it is naming, precisely, the criteria that process should be
scored against.

## 5. The acceptable boundary of automation

The analyzer should be **conservative and explainable**, not an
attempt at an omniscient static-analysis system. Concretely, this
means:

- It is acceptable, and by design, for the tool to say `ESCALATE` or
  `REQUIRE_ADDITIONAL_VALIDATION` more often than a more aggressive
  system would — false caution costs a human's review time; false
  confidence costs a real incident. The six investigations behind this
  document each independently reached the same conclusion when facing
  a choice between "detect more" and "stay safe": detecting more was
  rejected whenever it required guessing, framework-specific
  special-casing, or unbounded precision loss.
- It is **not** acceptable for the tool to fabricate probability,
  invent a "likely cause" for an ambiguous failure, silently treat a
  missing signal as a clean one, or expand its own discovery mechanism
  in a way that cannot be explained without reference to one specific
  repository, library, or filename.
- Automation stops exactly where evidence stops. Beyond that boundary,
  the tool's job is to say so clearly (`UNKNOWN`, `insufficient
  evidence`, an `IMPORTANT UNKNOWNS` line) and hand off to a human — not
  to close the gap with a heuristic dressed up as a discovery.

## Product philosophy

**ImpactTestAI should provide evidence-backed impact analysis and
validation, not certainty where the available evidence cannot support
it.**

The investigation program that led to this document established six
concrete, evidenced boundaries consistent with that philosophy:

- **Pipeline failures** → handle safely rather than crash
  ([`docs/decisions/PIPELINE_FAIL_SAFE_DESIGN.md`](decisions/PIPELINE_FAIL_SAFE_DESIGN.md)).
- **CI workflow naming** → generic discovery was justified and
  implemented (`TOOL_VERSION 0.10.0-pilot`'s changelog in
  `slice/analyze_change.py`; investigation record kept on branch
  `investigate/ci-workflow-discovery`).
- **CI window crowd-out** → complexity/cost currently outweighs
  demonstrated benefit (investigation record on branch
  `investigate/ci-window-crowd-out`).
- **Environment classification** → don't guess from ambiguous failures
  (investigation record on branch
  `investigate/environment-failure-classification`).
- **Indirect auth discovery** → don't introduce framework-specific
  heuristics (investigation record on branch
  `investigate/indirect-auth-discovery`).
- **Insufficient evidence** → escalate rather than manufacture
  confidence (structural, verified in §3 above, and enforced by
  regression tests going back to the 0.9.0 milestone).

That is a coherent, deliberately-bounded product — not an unfinished
analyzer waiting for its next feature.

---

## Using this document

This specification defines the contract. A future engineering pass
should evaluate the *current implementation* against it and identify
only the gaps that are both real and material — not treat every "not
yet reachable" or "not yet generic enough" line above as an implicit
backlog. Several of the boundaries in §2 are permanent, deliberate
product decisions, not temporary gaps.
