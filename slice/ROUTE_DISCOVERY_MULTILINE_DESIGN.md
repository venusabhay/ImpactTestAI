# Route discovery: formatting-independent span detection (design)

**Status: design, written before implementation, per the mandatory process.**

## Problem

`find_route_registrations()` currently detects a route call with one regex,
matched **per source line**:

```python
ROUTE_CALL_RE = re.compile(r"\b(\w+)\.(get|post|put|delete|patch|all)\(\s*[\"'`](/[^\"'`]*)[\"'`]")
...
for i, line in enumerate(lines):
    m = ROUTE_CALL_RE.search(line)
```

This requires the receiver, method, opening paren, **and** the path string
literal to all appear on the same physical line. Any call formatted with the
path argument on a following line — the default style produced by
Prettier/Standard for multi-argument calls, and the style used throughout a
held-out Fastify repository and roughly two-thirds of a held-out Express
repository's route files in the v8 round — is never matched at all, silently.
Measured impact: 0/9 and 7/21 real route-registration call sites detected in
those two repositories respectively.

The line-based match was never a deliberate scope decision; it was an
artifact of matching the whole call shape (including the path) with one
single-line regex. The fix is to decouple *finding the call* from *reading
its arguments*.

## Approach

Two independent passes, replacing the single combined regex:

1. **Find the call site.** A narrow regex matches only `receiver.method(` —
   the receiver, the HTTP-method name, and the opening paren. This is
   exactly the part that is guaranteed to appear together on one line in
   practice (nobody splits `router` from `.get(` from `(`); it carries no
   assumption about what follows.

   ```python
   ROUTE_METHOD_RE = re.compile(r"\b(\w+)\.(get|post|put|delete|patch|all)\(")
   ```

2. **Read the arguments, formatting-independent.** From the position of that
   opening paren, extract the balanced parenthesized span using the
   existing general-purpose `_extract_balanced()` helper (already used for
   the CommonJS object-literal export fix; it is delimiter-agnostic and
   string/template-literal aware, so it works identically whether the span
   is one line or fifty). Split that span into top-level, comma-separated
   arguments using the existing `_split_top_level()` helper — also already
   general-purpose, and depth/string aware, so an argument that is itself
   an object literal, a nested call, or a multi-line arrow function is
   never incorrectly split on an internal comma.

   The first top-level argument, trimmed, must be a quoted string starting
   with `/` — the same requirement the old regex enforced inline. If it
   isn't (e.g. `cache.get(someKey)`, a non-routing `.get()` call, or the
   first argument is missing/malformed), the call site is not a route
   registration and is skipped — no evidence fabricated, no crash.

   Every remaining top-level argument (whether it is positionally
   "middleware" or the final handler — both are already treated identically
   by the existing dependency-resolution mechanism, see
   `_resolve_arg_to_export()`) is kept as a `middleware_args` candidate if
   and only if it is, after trimming, a bare identifier or a dotted
   property-access chain (`[A-Za-z_$][A-Za-z0-9_$.]*`) — exactly the same
   filter the old `_extract_middleware_args()` applied per-token. An inline
   function, an arrow function, a call expression (`validate(schema)`), or
   an object literal (`{ preHandler: [...] }`) will never match this and is
   correctly excluded, matching current, unchanged scope: this milestone
   fixes *where* the call's arguments are found, not *what kinds* of
   arguments are understood as middleware.

3. **Source location.** `start_line` is the line of the `receiver.method(`
   match. `end_line` is the line containing the balanced span's closing
   paren (found by `_extract_balanced()`), computed via a small
   `\n`-counting helper rather than manual line-splitting — correct
   regardless of how many lines the call spans.

## Why this is generic

- Both helpers used (`_extract_balanced`, `_split_top_level`) are already
  general-purpose (not written for this milestone, not aware of routes,
  method names, or any repository) and are reused as-is.
- The receiver and method-name matching is unchanged: any identifier,
  followed by `.get/.post/.put/.delete/.patch/.all(` — `app`, `router`,
  `server`, `fastify`, or any arbitrary name.
- No repository name, filename, or property name appears anywhere in the
  implementation.
- The middleware-argument filter (bare/dotted identifier only) is
  unchanged from the current, already-shipped behavior — this is a span-
  detection fix, not a change to what counts as a dependency.

## What this deliberately does not do

- Does not parse or understand config-object route options (Fastify's
  `{ preHandler: [...] }` convention) — that is a separate, already-
  documented limitation (v8 report, Remaining Limitations) and a candidate
  for a future, separate milestone, not this one.
- Does not add any AST/parser dependency.
- Does not change `RiskAssessment`, `probability` semantics, `risk_level`
  thresholds, or the `ESCALATE`/`REQUIRE_ADDITIONAL_VALIDATION`/`ACCEPT`
  rules in `analyze_change.py`. Those files are untouched except for the
  `TOOL_VERSION`/`POLICY_VERSION` bump and its changelog comment.
- Does not touch `find_exported_names()`, `_resolve_arg_to_export()`,
  `_whole_module_import_aliases()`, or `strip_comments()` — those are
  unrelated to *finding* a route call and are reused unmodified.

## Risk / edge cases considered

- **Unbalanced/truncated input** (e.g. a file cut off mid-call): 
  `_extract_balanced()` returns `None`; the call site is skipped, not
  crashed on and not fabricated as a route.
- **A non-routing `.get()` call** (`cache.get(key)`, `Map.get(k)`): excluded
  by the same "first argument must be a `/`-prefixed string literal" check
  the old regex already enforced — no new false-positive surface.
- **Comments containing code-shaped text**: unaffected — `strip_comments()`
  still runs first, exactly as before.
- **Nested route-like calls** (a route handler that itself registers a
  route, e.g. dynamic sub-router mounting): each occurrence of
  `receiver.method(` in the text is matched independently by `finditer`,
  so nested calls are each detected on their own merits — this is a
  strict superset of the old per-line behavior, not a change in kind.
