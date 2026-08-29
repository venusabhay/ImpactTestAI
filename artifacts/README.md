# artifacts/

Generated run output only — never curated by hand, never committed
except this file. Every analyzer execution's immutable
`report.md`/`audit.json`/`metadata.json` is written here under
`<organization>/<repository>/<run_id>/`, per the Artifact History
milestone (see [`docs/decisions/ARTIFACT_HISTORY_DESIGN.md`](../docs/decisions/ARTIFACT_HISTORY_DESIGN.md)).

Everything under this directory except this README is `.gitignore`d.
GitHub Actions runs preserve their own artifacts via the workflow's own
artifact storage (see `.github/workflows/run-analysis.yml`), not by
committing them here.

If a run's output is worth keeping as a permanent, reviewable record —
a pilot case, an investigation's evidence — copy it into
[`pilot/`](../pilot/README.md) instead of leaving it here.
