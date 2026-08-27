# ImpactTestAI

A change-risk intelligence and validation decision platform: given a code change, it determines what might be affected, assesses risk from available evidence, decides what validation is actually needed, runs what it can, and reports an explainable recommendation — while clearly separating what's observed from what's inferred, and what's unknown from what's been checked.

## If you're here to try the pilot

**Start with [`slice/PILOT.md`](slice/PILOT.md).** It's a short, non-technical guide — you don't need anything below this line to use it. After you've run it a few times, please fill out [`slice/PILOT_FEEDBACK_TEMPLATE.md`](slice/PILOT_FEEDBACK_TEMPLATE.md).

## Repository layout

- [`slice/`](slice/) — the implementation: the analyzer (`analyze_change.py`), its test suite, CI fixtures, generated reports, and pilot documentation. This is the only part most people need.
- [`design/`](design/) — the architecture and domain-contract documents (`design1.md`–`design9.md`), the business vision, and the vertical-slice milestone record. Frozen; not needed to use the pilot.
- [`.github/workflows/`](.github/workflows/) — `pilot-ci.yml` (runs the analyzer's own tests on every push/PR) and `run-analysis.yml` (the on-demand workflow teams use to analyze their own repository — see PILOT.md).

## What this is not, yet

This is a pilot, not a finished product. It reads a target repository read-only, executes that repository's own tests, and reports — it does not fix code, write tests, commit, push, merge, or deploy anything. It discovers a repository's structure from evidence (`package.json` files, route-registration calls) rather than assuming any fixed layout — see `slice/PILOT.md` for what it can and can't currently recognize. Where it doesn't have enough evidence to say something with confidence, it says `UNKNOWN` rather than guessing — that's deliberate, not a limitation to work around.
