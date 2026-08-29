# Validation-command ancestor fallback: design

**Real, observed gap driving this milestone:**
[`pilot/reports/2026-08-29-milestone-a-generalization.md`](../../pilot/reports/2026-08-29-milestone-a-generalization.md),
Cases 2 (`vitejs/vite`, real commit `ee644014aa`) and 3
(`apache/superset`, real commit `de33efae98`) — two independent, real,
active repositories where the changed component (`packages/vite`;
`superset-frontend/plugins/plugin-chart-table`) has no `"test"` script
of its own, while a real, meaningful `"test"` script exists at an
ancestor directory (the repository root; `superset-frontend/`) and is
what each repository's own real CI actually runs for exactly this kind
of change. Before this milestone, `build_validation_decision()` only
ever checked the changed component's own `package.json` for a `"test"`
script; finding none, it reported `NOT AVAILABLE ... no package.json
test script` and escalated — technically honest (nothing was
fabricated), but a real coverage miss: validation that existed, and
passed in real CI, was never even considered.

A third, weaker signal (`apollographql/apollo-server`, Case 5) showed
the same underlying asymmetry narrowly avoided only by incidental luck
in that specific diff's shape (it happened to also touch a root-owned
changeset file, which is what made the repository root a "changed
component" and its test script reachable at all under the *prior*
mechanism).

## Scope

Narrow, evidence-driven, and deliberately not a general "search the
repo for any usable test command" feature: when the component a change
lands in has no `"test"` script of its own, walk its real filesystem
ancestors toward the repository root and use the **nearest** one that
does. Nothing else about how validation is selected, executed, or
judged changes.

## 1. What constitutes an "applicable ancestor validation command"?

A directory that is:

1. A genuine **filesystem ancestor** of the changed component's own
   directory — the changed component's `root_dir` is that directory,
   or a path beneath it. A sibling or cousin directory is never
   eligible, no matter how close by it looks in the repository tree or
   whether it happens to have its own real test script (real evidence:
   `nodejs/undici` in the same pilot round is a single-package
   repository with no ancestor at all above it; nothing there should
   ever, or could ever, borrow a script from an unrelated directory).
2. Already a **discovered component** — i.e. it has its own
   `package.json`, exactly the same evidence `find_components()`
   already uses to define component boundaries everywhere else in this
   analyzer. No new discovery mechanism, no scanning for arbitrary
   `package.json` files outside that existing definition.
3. Has a real, literal `"test"` key under that `package.json`'s
   `"scripts"` object — the exact same test this analyzer already
   applies to the changed component itself. Nothing about what counts
   as "having a test script" changes; only *where* the analyzer is
   willing to look for one does.

Implemented as `discovery.find_validation_ancestor(repo,
component_root_dir, components)` — see `slice/discovery.py`.

## 2. Is this the same question `find_workspace_root()` already answers?

No, deliberately not, and reusing it would have been the wrong call.
`find_workspace_root()` requires a **declared package-manager
relationship** (an ancestor `package.json`'s `"workspaces"` field
actually listing this component) because redirecting an *install* has
real side effects — installing the wrong dependencies from the wrong
place. Finding an ancestor's *test script* worth trying is a much
lower-stakes question with no such side effect, and — critically —
**both real repositories this milestone is evidence-driven by fall
outside `find_workspace_root()`'s own rule**: `vitejs/vite` is a real
pnpm-only repository (workspace membership declared via
`pnpm-workspace.yaml`, a format `find_workspace_root()` disclosedly
does not read — see `WORKSPACE_AWARE_INSTALL_DESIGN.md` §2), and
`apache/superset`'s top-level repository has no root `package.json` at
all (it's a Python project; `superset-frontend/` is its own,
self-contained real root for the JS side). Gating this fallback on
`find_workspace_root()` would have produced `None` for both real cases
that motivated it, defeating the fix. The two mechanisms answer
different questions and stay independent: this milestone changes
nothing about workspace-install redirection, and workspace-install
redirection changes nothing about this fallback.

## 3. Does the nearest valid ancestor win, or can a more distant one (e.g. the repository root) be picked instead?

The nearest one always wins. `find_components()` already returns every
discovered component sorted deepest-root-first; `find_validation_ancestor()`
filters that same list down to genuine ancestors of the changed
component and returns the *first* one (by construction, the nearest)
that has a `"test"` script — walking past any ancestor that doesn't,
without ever preferring a more distant ancestor that does over a nearer
one that doesn't yet have one. A repository where *both* an
intermediate ancestor and the repository root have real test scripts
(a realistic monorepo shape) will always select the intermediate one,
never jump straight to the root just because the root would also
technically qualify — this is directly regression-tested (see
`test_nearest_ancestor_wins_over_a_more_distant_one_that_also_qualifies`
in `test_discovery.py`).

## 4. What happens when the component already has a valid local command?

Nothing changes. `find_validation_ancestor()` is only ever consulted
when the component's own `package.json` has no `"test"` script — the
existing, byte-for-byte-unchanged code path for a component with its
own valid command is completely untouched, confirmed by a dedicated
regression test
(`test_build_validation_decision_uses_component_local_test_script_unchanged`)
asserting the exact prior reason wording and the absence of any new
fallback-related field.

## 5. What happens when no applicable ancestor exists at all?

Exactly the same as before this milestone: the validation is rejected
with `No 'test' script found for component '<name>' (...)`, nothing is
selected, and (assuming no other validation was selected either)
`final_recommendation()`'s existing `no_validation_ran` path forces
`ESCALATE` — unchanged code, unchanged behavior, confirmed by
`test_build_validation_decision_rejects_when_no_ancestor_has_a_test_script`.
This covers both "no ancestor component exists above this one at all"
and "ancestor components exist but none of them has a test script"
identically, since both mean the same thing for this fallback's
purposes: there is nothing safe to redirect to.

## 6. Can an unrelated ancestor's or sibling's script be selected by mistake?

No. Because eligibility requires genuine filesystem containment (§1.1)
checked against the *changed* component's own directory specifically,
a sibling component's real test script — even one sitting right next
to the changed component in the same parent directory — is never
considered, regardless of how "close" it looks. Directly regression-tested
at both the mechanism level
(`test_sibling_component_with_a_test_script_is_never_selected`,
`test_discovery.py`) and the integration level
(`test_build_validation_decision_does_not_select_a_sibling_components_script`,
`test_analyze_change.py`).

## 7. What is disclosed to a report reader when the fallback fires?

Two things, both real and traceable, not summarized away:

- The `RECOMMENDED VALIDATION` line's prose explicitly says the
  component has no test script of its own and names the ancestor
  actually used (`'<component>' component has no test script of its
  own; its nearest ancestor with one, '<ancestor>', is the best
  available real validation for this change`).
- A new, machine-readable `validated_via_ancestor` field — set on the
  selected validation itself and propagated onto the executed
  outcome (mirroring exactly how `install_workspace_root` already
  discloses a workspace-install redirect) — surfaced in both
  `report.md` (`validated via ancestor component's test script at:
  ...`) and `audit.json`. `"."` denotes the repository root itself,
  matching `install_workspace_root`'s own existing convention exactly.

## What this does not do

Does not change which files count as route/middleware evidence, how
components are discovered in the first place, `find_workspace_root()`
or workspace-install redirection, risk/confidence scoring,
`final_recommendation()`, `POLICY_VERSION`, or any `.github/workflows/`
file. Does not add a new package-manager abstraction, retries, or any
repository-specific special case — `find_validation_ancestor()`
contains no reference to `vite`, `superset`, or any other specific
repository, package, or dependency name. Does not attempt to run a
separate build/compile step before testing (the OpenTelemetry
build-step observation from the same pilot round is explicitly a
follow-up observation, not addressed here — see the disposition
document). Does not extend pnpm support in any way: a real ancestor
`package.json` is still only ever read for its `"scripts"` object here,
never for pnpm-specific workspace membership, and installing at a real
pnpm-managed ancestor directory remains exactly as unsupported as it
was before this milestone (see the disposition document's real-world
verification for a concrete example of this boundary holding).
