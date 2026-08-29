# ImpactTestAI

A change-risk intelligence and validation decision platform: given a code change, it determines what might be affected, assesses risk from available evidence, decides what validation is actually needed, runs what it can, and reports an explainable recommendation — while clearly separating what's observed from what's inferred, and what's unknown from what's been checked.

## If you're here to try the pilot

**Start with [`PILOT.md`](PILOT.md).** It's a short, non-technical guide — you don't need anything below this line to use it. After you've run it a few times, please fill out [`pilot/PILOT_FEEDBACK_TEMPLATE.md`](pilot/PILOT_FEEDBACK_TEMPLATE.md).

**If you want to know what ImpactTestAI promises (and explicitly does not promise) before relying on it**, see [`docs/PRODUCT_VALIDATION_SPEC.md`](docs/PRODUCT_VALIDATION_SPEC.md) — the product contract, including what evidence justifies each outcome it can report.

**If you're picking up engineering on this project**, start with [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) — the current repository state, completed milestones, deferred findings, and the one next action, before consulting anything else.

## Repository layout

- [`slice/`](slice/) — the implementation: the analyzer (`analyze_change.py`), its test suite, and CI fixtures. This is the only part most people need to read.
- [`docs/`](docs/README.md) — engineering history and reasoning: the original design narrative, and one document per engineering decision (design docs, proposals, dispositions). Not needed to use the pilot.
- [`pilot/`](pilot/README.md) — evidence from running the analyzer against real repositories: individual case results, investigations, and summary reports.
- [`artifacts/`](artifacts/README.md) — where a run's generated `report.md`/`audit.json` land; gitignored except for its own README.
- [`.github/workflows/`](.github/workflows/) — `pilot-ci.yml` (runs the analyzer's own tests on every push/PR) and `run-analysis.yml` (the on-demand workflow teams use to analyze their own repository — see `PILOT.md`).

## What this is not, yet

This is a pilot, not a finished product. It reads a target repository read-only, executes that repository's own tests, and reports — it does not fix code, write tests, commit, push, merge, or deploy anything. It discovers a repository's structure from evidence (`package.json` files, route-registration calls) rather than assuming any fixed layout — see [`PILOT.md`](PILOT.md) for what it can and can't currently recognize. Where it doesn't have enough evidence to say something with confidence, it says `UNKNOWN` rather than guessing — that's deliberate, not a limitation to work around.
