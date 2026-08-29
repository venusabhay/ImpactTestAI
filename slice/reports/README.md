# slice/reports/

This directory is intentionally near-empty. It exists only so that
`.github/workflows/pilot-ci.yml`'s and `run-analysis.yml`'s hardcoded
`--out slice/reports/pilot-*...` output paths have somewhere to write
their generated (already `.gitignore`d) smoke-test/run reports on a
fresh checkout — those files are ephemeral CI output, not retained here.

Curated pilot evidence (case reports, investigation findings, milestone
reports) previously kept under this directory has moved to
[`../../pilot/`](../../pilot/README.md). Do not add new curated
`.md`/`.json` evidence here — it belongs under `pilot/`.
