# docs/

Engineering history and reasoning — not product usage documentation
(that's the root [`README.md`](../README.md), [`slice/README.md`](../slice/README.md),
and [`PILOT.md`](../PILOT.md)) and not pilot evidence (that's
[`pilot/`](../pilot/README.md)).

- **[`PRODUCT_VALIDATION_SPEC.md`](PRODUCT_VALIDATION_SPEC.md)** — the
  current product contract: what ImpactTestAI promises, what it
  explicitly does not, what evidence justifies each outcome it can
  report, and how to measure whether a pilot round found it useful.
  Start here if you want to know what the tool is supposed to do before
  digging into why any specific piece of it works the way it does.
- **[`design/`](design/)** — the sequential architecture/domain-contract
  narrative (`business-vision.md`, `design1.md`–`design9.md`) that shaped
  the platform before and during implementation. Historical; later
  documents supersede earlier ones on points of disagreement.
- **[`decisions/`](decisions/)** — one document per shipped or explicitly
  deferred engineering decision: design docs written before
  implementation, proposals, and post-implementation dispositions. If you
  want to know *why* a specific behavior exists, look here first.
- **[`architecture/`](architecture/)** — reserved for a maintained,
  current-state architecture reference, if one is ever written
  separately from the historical `design/` narrative. Empty today.

Nothing here is needed to use the tool. Nothing here should be deleted
just because it's old — it's the record of why the product looks the way
it does.
