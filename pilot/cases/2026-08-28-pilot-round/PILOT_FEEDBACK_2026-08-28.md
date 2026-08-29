# ImpactTestAI Pilot Feedback — Internal pilot run (engineering-conducted)

Filled out per `PILOT_FEEDBACK_TEMPLATE.md`'s structure, based on the 5 representative runs in `PILOT_FINDINGS_REPORT.md`. This round was run by engineering against external repositories, not a real product team against their own repository — treat this as a template dry-run plus a first data point, not a substitute for actual team feedback.

## Summary table

| Run ID | Change tested | Useful finding? | Unnecessary recommendation? | Missed issue? | Would use again? |
| --- | --- | --- | --- | --- | --- |
| `20260828T183544Z-4d3d18b5` | Comment typo fix, `express-es6-rest-api` | No — correctly low-stakes, nothing to learn | Arguably yes — `REQUIRE_ADDITIONAL_VALIDATION` after the only check already passed | No | Yes |
| `20260828T185410Z-ce54f94b` | Mongoose `.remove()`→`.deleteOne()`, `node-express-mongoose-typescript-boilerplate` | Yes — but the finding was about the *repo's* env setup, not the code | No — `ESCALATE` on a real test failure is correct even though the cause is environmental | No — but see "missed" below: it did not distinguish env failure from real regression | Yes, with the env-var caveat in mind |
| `20260828T190048Z-ce243c6f` | "add bearerAuth", `node-express-mongoose-typescript-boilerplate` | Yes — precise 8-route middleware-dependency discovery, real find | No | **Yes** — `passport.ts` itself, arguably the most security-relevant file touched, produced zero discoverable impact | Yes |
| `20260828T183918Z-07ef5c99` | `/verify` caching regression, `social-media-mini` | Yes, strongly — caught a real, reproducible security regression | No | No | Yes, without reservation |
| `20260828T183932Z-c30907be` | Frontend password-confirmation validation, `user-management-app` | Yes — correctly declined to invent evidence where none exists | No | No | Yes |
| *(no run ID — process crashed)* | CI-history fetch, `node-express-mongoose-typescript-boilerplate` | N/A | N/A | **Yes** — the crash itself is the missed issue | Not applicable until fixed |
| *(no run ID — process crashed)* | `npm install`, same repo | N/A | N/A | **Yes** — same | Not applicable until fixed |

**Rollup:**

| Team | Changes tested | Useful findings | Unnecessary recommendations | Missed issues | Would use again? |
| --- | --- | --- | --- | --- | --- |
| Engineering (pilot dry-run) | 5 completed + 2 crashed | 3 of 5 completed runs | 1 of 5 (arguable, case 1) | 1 real detection gap (`passport.ts`), 2 crashes | Yes, contingent on the crashes being investigated |

## Questions

1. **Did this tell us something useful?** Yes, most clearly in the `social-media-mini` case — a real, reproducible security regression, with the exact evidence needed to understand why. The two crashes were also useful, in the sense that we'd rather find them now than have a pilot team find them first.

2. **Did it change what we would have tested?** In the `bearerAuth` case, yes — the 8-route middleware-dependency discovery surfaced a wider blast radius than a quick glance at the diff would suggest, which is a genuine "this changes my testing priority" result.

3. **Did it save us time?** For the trivial and insufficient-evidence cases (1 and 5), it confirmed quickly what a human would have guessed anyway — a small time save, mostly in confidence rather than raw hours. For case 4, it did real work a human would otherwise have had to build (the cross-service test) by hand.

4. **Did it identify something our normal process missed?** Yes, twice, in different ways: (a) `social-media-mini`'s stale-cache authorization bypass, which no existing test in that repo could have caught; (b) the two crashes themselves, which a normal manual review of "does the report look reasonable" would never surface, since there's no report to look at when it crashes.

5. **Did it ask us to do unnecessary work?** Borderline, once: recommending `REQUIRE_ADDITIONAL_VALIDATION` for a one-character comment fix, after the only available check had already run and passed. Technically consistent with the disclosed policy, but it's the kind of result that could make a first-time user distrust the tool's calibration if it's the first thing they see.

6. **Did we trust the explanation?** Yes, in every completed run — every report showed its exact evidence and named its unknowns rather than asserting confidence it didn't have. The one place trust would be misplaced without reading the fine print: a `FAILED` validation result doesn't always mean "the change broke something" — twice this round it meant "the test suite couldn't even start" (missing env var; no test files yet), and the top-line label doesn't make that distinction as clearly as the classification text underneath it does.

7. **Would we use this again?** Yes — with the caveat that the two crashes need to be understood and addressed before this goes in front of a pilot team who doesn't already know to expect them.

## Anything else

The single most important thing from this round isn't in the summary table at all: two of seven attempted analyses (2 of 5 "case" repositories, hit while gathering CI history and while installing dependencies) crashed outright with a raw Python traceback and produced *no artifact whatsoever* — not even an honest `ESCALATE`. Both are outside the specific validation-timeout mechanism this milestone just finished hardening, which only covers the one subprocess call it was scoped to touch. A pilot team hitting either of these would see a failed GitHub Actions run with no usable output and, per `PILOT.md`'s own guidance, correctly conclude "that's a bug in the tool" — which, in this case, it would be right about.
