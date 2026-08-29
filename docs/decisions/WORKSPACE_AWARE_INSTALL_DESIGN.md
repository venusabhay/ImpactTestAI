# Workspace-aware validation installation: design

**Written before implementation.** Real, observed failure driving this
milestone: `socketio/socket.io`'s `packages/socket.io-parser` package,
real commit `7c6ef571` ("fix(parser): reject binary packets with zero
attachments") — `npm install` scoped to the component's own directory
left `prettier` (a devDependency this npm-workspaces repository hoists
to its root) unavailable, producing `FAILED`, exit 127, `sh: prettier:
command not found`, before the real test suite ever ran. First
documented in `pilot/reports/2026-08-29-product-validation-pilot.md`
(Case 3); reproduced fresh for this milestone before any code changed.

## Scope

Not a general-purpose monorepo engine. One narrow question: when the
changed component is a declared member of an npm or Yarn workspace,
install at that workspace's root instead of inside the component alone
— nothing else about how validation is selected, executed, or judged
changes.

## 1. How is a workspace detected?

Via the standard `"workspaces"` field in an ancestor `package.json` —
the same field npm (7+) and Yarn (classic and berry) both read to
define workspace membership. `discovery.find_workspace_root()` walks
upward from the component's own directory, skipping any ancestor
`package.json` that doesn't declare `"workspaces"` at all (the normal
shape of every ordinary member package in a real workspace — confirmed
directly: every package under `socketio/socket.io/packages/*` has a
plain `package.json` with no `"workspaces"` field of its own; only the
repository root does), and stops at the first ancestor that does,
checking whether the component's own path actually appears among its
declared patterns.

## 2. Which package managers/conventions are supported?

npm workspaces and Yarn (classic and berry) workspaces — both read the
identical `"workspaces"` field, in either its plain-array form
(`["packages/*"]`, npm's only supported shape, confirmed as the real
shape `socketio/socket.io`'s own root `package.json` uses) or Yarn
classic's equivalent `{"packages": [...], "nohoist": [...]}` object
form. Both a bare wildcard pattern (`"packages/*"`) and an exact,
non-wildcard member path are supported, matched segment-by-segment
(`"*"` matches exactly one path segment, not an arbitrary number —
Python's own `fnmatch` would otherwise let `*` cross `/`, which is not
how npm/Yarn workspace globs behave). Recursive `**` patterns are not
supported. **pnpm is explicitly not supported** — it declares
workspace members in a separate `pnpm-workspace.yaml` file, a different
convention this milestone does not read. This is a disclosed scope
boundary: adding YAML parsing and a second, structurally different
detection path for one more package manager is exactly the "broader
package-manager abstraction" this milestone was told to avoid building
if the narrow rule didn't already cover it. Revisit only if real pilot
evidence shows pnpm-hoisting causing the same failure shape.

## 3. What happens when no workspace is detected?

`find_workspace_root()` returns `None`. `run_validation()` then uses
`install_dir = svc_dir` — the exact expression and exact value used
before this milestone existed. No new code path is exercised; behavior
is byte-for-byte identical to `main` before this change (verified in
§5 below and by the "no workspace" test case).

## 4. What happens when workspace metadata is ambiguous or unsupported?

Treated identically to "no workspace detected" — `None`, same fallback.
This covers: an ancestor `package.json` exists but has no `"workspaces"`
field (kept walking past it, correctly, since this is the normal shape
of an ordinary workspace member); an ancestor declares `"workspaces"`
but its patterns don't actually list this component (stops there,
returns `None` — does not keep searching more distant ancestors, since
the nearest declaration is authoritative); the field is present but
in a shape this milestone doesn't parse (neither a list nor a
`{"packages": [...]}` object); or the file can't be read/parsed at all.
None of these cases guess at a workspace root that hasn't been
confirmed by matching a real declared pattern.

## 5. Does the existing non-workspace behavior remain byte-for-byte equivalent?

Yes. `find_workspace_root()` is a pure, additional read of repository
metadata that produces `None` for the entire pre-existing test corpus
and every non-workspace repository; when it returns `None`,
`install_dir` collapses to exactly `svc_dir`, the same identifier the
install call used before this milestone, with no other change to the
call itself (same `shell=True`, same timeout, same `env`, same
exception handling). Confirmed by the full 124-test suite passing
unchanged, and directly by this milestone's own "no workspace" negative
test.

## 6. Can the solution accidentally install unrelated packages or materially expand validation scope?

Not in the sense of installing something not already part of this
repository's own declared dependency graph. Running `npm install` at a
genuine, declared workspace root installs the *entire* workspace's
dependencies (all member packages, not only the changed one) — this is
npm/Yarn's own standard workspace-install behavior, not something this
analyzer adds on top. That is a real, disclosed side effect worth
naming plainly: a workspace-root install can take longer and touch more
of the filesystem than installing one package alone would. It is not
scope expansion in the sense the instruction warns against — no
repository-specific exception, no unrelated third-party package, and no
change to which routes/components are discovered or which validation
command is *selected* and judged. The validation command that actually
runs, and the component it runs in, are completely unchanged; only
where its dependencies get installed from changes.

## 7. What happens when workspace installation itself fails?

Exactly the same fail-safe handling introduced in the 0.9.0 milestone,
reused unmodified: a timeout still produces `INCONCLUSIVE` /
`INFRASTRUCTURE (dependency install timed out)`; a non-zero exit still
produces `INCONCLUSIVE` / `INFRASTRUCTURE (dependency install failed)`;
either way, validation is not silently attempted against dependencies
known to be unavailable (`continue`, unchanged), and `INCONCLUSIVE`
still forces `ESCALATE` (unchanged, `final_recommendation()` not
touched). The only difference from before this milestone is *where*
that same install command ran (`cwd`); its own success/failure/timeout
handling is identical code, now additionally annotated with
`install_workspace_root` on the outcome when a workspace redirect
actually happened, so a report reader can see why installation ran
somewhere other than the component's own directory.

## What this does not do

Does not build a dependency-graph engine, a general monorepo model, or
support for any package manager beyond npm/Yarn's shared
`"workspaces"` field. Does not change risk scoring, confidence scoring,
`final_recommendation()`, `POLICY_VERSION`, service/component
discovery, or route-label composition. Does not add retries. Does not
special-case `socketio/socket.io`, `prettier`, or any other specific
repository, package, or dependency name anywhere in the implementation
— confirmed directly by inspecting the diff.
