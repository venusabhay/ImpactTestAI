# Product validation gap disposition

Decisions arising from the 2026-08-29 product validation pilot
([`pilot/reports/2026-08-29-product-validation-pilot.md`](../../pilot/reports/2026-08-29-product-validation-pilot.md)),
scored against [`docs/PRODUCT_VALIDATION_SPEC.md`](../PRODUCT_VALIDATION_SPEC.md).
Nothing here has been implemented — these are dispositions, not
implementation tickets.

| Finding | Evidence | User impact | Decision |
|---|---|---|---|
| Route labels lose mount prefixes | A real commit's 3 distinct routes (`GET /`, `GET /api/v1`, `GET /api/v1/emojis`) all rendered as `GET /`; the same root cause under-credited genuinely passing, directly-relevant test coverage as "no test file evidence found" | Can make impact evidence confusing or incomplete | **Evaluate for implementation** |
| Workspace/hoisted dependency installation | Real `socketio/socket.io` (`socket.io-parser` package) validation failed before any test ran — `prettier: command not found`, exit 127 — because `npm install` was scoped to the sub-package directory, not the workspace root where its devDependencies are hoisted | Can prevent meaningful validation in monorepos | **Evaluate for implementation** |
| CI rate-limit tension | Recurred organically again this round (94 real workflow runs found for `expressjs/cors`, most job-detail fetches rate-limited) | Existing known limitation | **Remain deferred** |

All other previously-deferred items — environment classification,
indirect auth discovery, CI window crowd-out, retries, CI rate-limit
mitigation, `ACCEPT` policy, broader risk-model changes — are
unaffected by this pilot and remain exactly as deferred.

## Ranking the two "evaluate" candidates

Applying the stated test — implement only if a gap (1) affects a core
product promise, (2) occurs in realistic repositories, (3) materially
reduces usefulness or trust, and (4) has a reasonably narrow, generic
fix:

**#1 — Route-label composition.** Satisfies all four with the least
uncertainty: it sits directly inside impact discovery (a core promise),
the mount-prefix pattern it fails on (`app.use(prefix, router)`) is
ordinary, ubiquitous Express structure rather than an edge case, it
demonstrably corrupted two separate report sections from one real
commit, and the shape of a fix is conceptually narrow — compose the
prefixes already established by existing `app.use()`/`router.use()`
registrations when rendering a route's path, without introducing any
new relationship type or repository-specific knowledge. Narrower in
concept than every mechanism rejected in the indirect-auth-discovery
investigation, because it reuses the already-parsed route-registration
primitive rather than following a new kind of link.

**#2 — Workspace-aware installation.** Also satisfies (1)–(3): it
touches validation execution (a core promise), monorepos/workspaces are
common in real JS/TS repositories, and a false `FAILED` indistinguishable
from a real regression is a serious, trust-relevant failure mode. It is
ranked second because (4) is not yet established: whether the *correct*
fix is "detect an npm/yarn/pnpm workspace and install at the workspace
root instead of the component directory" — and, if so, whether that
composes safely with this project's existing per-component validation
model, or trades one problem (a false failure) for another (installing
and potentially slowing validation for an entire workspace to test one
package) — is an open design question, not a demonstrated-narrow fix.
The existing fail-safe behavior here is already honest (a real `FAILED`
with real evidence, not a crash or a fabrication); the open question is
whether coverage loss is common and costly enough to justify resolving
that design question, not whether the current behavior is unsafe.

## What this document does not do

It does not commit to building either candidate. Per the pilot's
instruction and this project's established discipline, "evaluate for
implementation" means a future engineering pass may investigate route-
label composition first (its narrower, more contained shape gives it the
current lead) and treat workspace-aware installation as a genuine
open design question rather than a queued fix — starting, as always
in this project, with a design/proposal document before any code
changes, not with this disposition itself.
