# pilot/investigations/

One subdirectory per investigation: a question about the analyzer's
real-world behavior, answered with evidence from real repositories,
*before* deciding whether to build anything — see
[`docs/decisions/`](../../docs/decisions/) for what was actually decided
as a result.

Current investigations:

- **[`architecture-discovery/`](architecture-discovery/)** — the
  held-out and regression-verification rounds (v6–v9) that took
  `ADAPT_ARCHITECTURE_DISCOVERY` from an untested idea to an accepted
  baseline, plus the business checkpoint recorded along the way
  (`NEXT_MILESTONE.md`).

Investigations recorded only on their own branch (not yet reflecting a
merged decision) are not duplicated here — see the branch itself, e.g.
`investigate/ci-workflow-discovery`, `investigate/ci-window-crowd-out`.
