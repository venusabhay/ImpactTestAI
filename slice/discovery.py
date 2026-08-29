"""
Architecture discovery primitives (ADAPT_ARCHITECTURE_DISCOVERY).

Replaces two hardcoded assumptions from the original prototype
(services/<name>/ directory layout, app.METHOD(...) route syntax) with
evidence-based discovery: component boundaries from package.json presence,
route registrations from the general receiver.method(path, ...) Express
calling convention (any receiver name), and a new capability -- middleware/
dependency discovery -- that finds files used as middleware by routes
defined elsewhere, via exported-name usage rather than a specific filename.

Scope boundary (see docs/decisions/ARCHITECTURE_DISCOVERY_DESIGN.md): Node.js
repositories using an Express-style calling convention. Regex/text-based,
not a real parser -- disclosed false-negative risk on dynamic or
unconventional route registration is expected and reported, not
special-cased around.

Contains NO reference to any specific repository, filename, or route path.
"""
import fnmatch
import json
import os
import re

EXCLUDE_DIRS = {"node_modules", ".git", "coverage", "dist", "build", ".pytest_cache", "__pycache__"}

# Source file extensions this analyzer reads for route/middleware/export
# discovery. Found via held-out testing (ai-agents, a real TypeScript
# repository) that .ts/.tsx were silently never scanned -- an inherited gap
# from the original JS-only prototype, not a deliberate scope decision.
# The underlying route/export/import regexes are TS-syntax-compatible
# (type annotations don't break `receiver.method(path, ...)` or
# `export const x =` patterns), so extending the extension list is the
# correct, general fix -- not a repository-specific accommodation.
SOURCE_EXTENSIONS = (".js", ".jsx", ".ts", ".tsx")


def is_source_file(filename):
    return filename.endswith(SOURCE_EXTENSIONS)


def strip_source_extension(filename):
    for ext in SOURCE_EXTENSIONS:
        if filename.endswith(ext):
            return filename[: -len(ext)]
    return filename


def strip_comments(text):
    """Blanks out // line comments and /* */ block comments in JS/TS source
    text, without being fooled by // or /* appearing inside a string or
    template literal. Found necessary via held-out testing: a code-shaped
    example inside a comment was matched by the route scanner as a real
    route registration.

    A lightweight character-scanning state machine, not a real parser --
    consistent with this module's disclosed regex/text-based scope (see
    module docstring). Preserves line count and character offsets exactly
    (comment content is replaced with spaces, embedded newlines kept) so
    line-number reporting elsewhere in the analyzer is unaffected.
    """
    result = []
    i, n = 0, len(text)
    in_string = None  # None, or the quote/backtick character we're inside
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_string:
            result.append(ch)
            if ch == "\\" and i + 1 < n:
                result.append(nxt)
                i += 2
                continue
            if ch == in_string:
                in_string = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            in_string = ch
            result.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            end = text.find("\n", i)
            end = end if end != -1 else n
            result.append(" " * (end - i))
            i = end
            continue
        if ch == "/" and nxt == "*":
            close = text.find("*/", i + 2)
            end = close + 2 if close != -1 else n
            result.append("".join("\n" if c == "\n" else " " for c in text[i:end]))
            i = end
            continue
        result.append(ch)
        i += 1
    return "".join(result)

ROUTE_METHOD_RE = re.compile(r"\b(\w+)\.(get|post|put|delete|patch|all)\(")

_IDENTIFIER_ARG_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$.]*")

_PATH_ARG_RE = re.compile(r"[\"'`](/[^\"'`]*)[\"'`]")


# ---------------------------------------------------------------------------
# 1. Component discovery
# ---------------------------------------------------------------------------

def find_components(repo):
    """Every directory (excluding noise dirs) containing a package.json is a
    component root, regardless of its position in the tree or its parent's
    name. Returns components sorted deepest-root-first, so attribution
    (component_for_path) finds the most specific match."""
    components = []
    for dirpath, dirnames, _filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        if "package.json" in _filenames:
            rel = os.path.relpath(dirpath, repo).replace("\\", "/")
            rel = "" if rel == "." else rel
            name = None
            try:
                with open(os.path.join(dirpath, "package.json"), "r", errors="ignore") as f:
                    pkg = json.load(f)
                name = pkg.get("name")
            except (OSError, ValueError):
                pass
            if not name:
                name = os.path.basename(dirpath) if rel else os.path.basename(os.path.abspath(repo))
            components.append({"name": name, "root_dir": rel})
    components.sort(key=lambda c: len(c["root_dir"]), reverse=True)
    return components


def component_for_path(path, components):
    """Nearest (deepest) component root that is an ancestor of `path`
    (repo-relative). Returns None only if no component root exists at all
    (e.g. no package.json anywhere) -- an honest 'insufficient evidence'
    outcome, not a crash."""
    norm = path.replace("\\", "/")
    for c in components:
        root = c["root_dir"]
        if root == "":
            continue  # try the repo-root component last
        if norm == root or norm.startswith(root + "/"):
            return c["name"]
    for c in components:
        if c["root_dir"] == "":
            return c["name"]
    return None


def component_root_dir(name, components):
    for c in components:
        if c["name"] == name:
            return c["root_dir"]
    return None


# ---------------------------------------------------------------------------
# Workspace-root detection (workspace-aware validation installation
# milestone) -- see docs/decisions/WORKSPACE_AWARE_INSTALL_DESIGN.md.
#
# A component installed with `npm install` run only inside its own
# directory can fail on tooling the repository actually hoists to a
# workspace root (real pilot evidence: socketio/socket.io's
# socket.io-parser package failed with "prettier: command not found"
# before any real test ran, because prettier is a root-level
# devDependency npm workspaces hoists). This uses the standard,
# package-manager-level "workspaces" field in an ancestor package.json
# -- the same field npm and Yarn (classic and berry) both read -- not a
# heuristic and not specific to any repository. pnpm's separate
# pnpm-workspace.yaml convention is a disclosed, out-of-scope boundary,
# not silently ignored.
# ---------------------------------------------------------------------------

def _workspace_patterns(workspaces_field):
    """Normalizes a root package.json's "workspaces" field -- a bare
    list of glob patterns (the common, and npm's only supported, shape),
    or Yarn classic's equivalent {"packages": [...], "nohoist": [...]}
    object form -- into a plain list of pattern strings. Any other shape
    (including the field being absent) yields [] -- ambiguous/unsupported
    metadata is treated as "no workspace here," never guessed at."""
    if isinstance(workspaces_field, list):
        return [p for p in workspaces_field if isinstance(p, str)]
    if isinstance(workspaces_field, dict) and isinstance(workspaces_field.get("packages"), list):
        return [p for p in workspaces_field["packages"] if isinstance(p, str)]
    return []


def _matches_workspace_pattern(rel_dir, pattern):
    """One npm/Yarn workspace glob pattern (e.g. "packages/*", or an
    exact member path with no wildcard at all, as in socketio/socket.io's
    own package.json) matched against a path relative to the workspace
    root -- segment-by-segment, so "*" matches exactly one path segment,
    not an arbitrary number of them the way Python's fnmatch would let it
    cross "/". Recursive "**" patterns are not supported here -- a
    disclosed, narrow limitation, not silently guessed at."""
    if "**" in pattern:
        return False
    rel_parts = rel_dir.split("/")
    pat_parts = pattern.rstrip("/").split("/")
    if len(rel_parts) != len(pat_parts):
        return False
    return all(fnmatch.fnmatchcase(r, p) for r, p in zip(rel_parts, pat_parts))


def find_workspace_root(repo, component_root_dir):
    """Is `component_root_dir` (repo-relative; "" for the repo root
    itself) a declared member of an npm/Yarn workspace rooted at some
    ancestor directory? Walks upward from its parent, skipping any
    ancestor package.json that doesn't declare a "workspaces" field at
    all (an ordinary, non-root package -- the normal shape of every
    member of a real workspace), and stops at the first one that does,
    checking whether this component's path (relative to that ancestor)
    actually matches one of its declared patterns.

    Returns the workspace root's repo-relative directory ("" for the
    repo root itself) if `component_root_dir` is a genuine declared
    member; None otherwise -- covering both "no workspace exists
    anywhere above this component" and "a workspace root exists but
    doesn't declare this component" identically, since both mean the
    same thing for installation purposes: there is nothing here to
    safely redirect to, so fall back to installing at the component's
    own directory exactly as before this capability existed. Never
    walks above `repo`, and never guesses past the nearest ancestor that
    does declare "workspaces" -- if that one doesn't list this
    component, no further, more distant ancestor is consulted."""
    if not component_root_dir:
        return None  # the component IS the repo root; no ancestor to find
    current = os.path.dirname(component_root_dir.rstrip("/"))
    while True:
        pkg_path = os.path.join(repo, current, "package.json") if current else os.path.join(repo, "package.json")
        if os.path.isfile(pkg_path):
            try:
                with open(pkg_path, "r", errors="ignore") as f:
                    pkg = json.load(f)
            except (OSError, ValueError):
                pkg = {}
            if "workspaces" in pkg:
                patterns = _workspace_patterns(pkg.get("workspaces"))
                rel = (
                    os.path.relpath(component_root_dir, current).replace("\\", "/")
                    if current else component_root_dir
                )
                if any(_matches_workspace_pattern(rel, p) for p in patterns):
                    return current
                return None
        if current == "":
            return None
        current = os.path.dirname(current)


# ---------------------------------------------------------------------------
# 2. Route discovery (generalizes app.METHOD(...) to any receiver)
# ---------------------------------------------------------------------------

def _line_number_at(text, index):
    """1-indexed line number of the character at `index` in `text`."""
    return text.count("\n", 0, index) + 1


def _middleware_args_from_call(args):
    """Given the top-level arguments AFTER the path (already split by
    _split_top_level, so each one is exactly one argument regardless of how
    many lines or internal commas it spans), keeps whichever are bare
    identifiers or dotted property-access chains -- the general shape a
    middleware reference OR a class-instance-method final handler can take
    (see _resolve_arg_to_export). An inline function, arrow function, call
    expression (`validate(schema)`), or object literal
    (`{ preHandler: [...] }`) never matches this and is correctly excluded
    -- same filter _extract_middleware_args applied per-token, just fed
    exact arguments instead of a hand-sliced, formatting-sensitive string."""
    kept = []
    for arg in args:
        token = arg.strip()
        if _IDENTIFIER_ARG_RE.fullmatch(token):
            kept.append(token)
    return kept


def find_route_registrations(file_text):
    """Generalized, formatting-independent route detection: ANY
    receiver.method(path, ...) call, not only app.method(...), regardless
    of how the call's arguments are split across lines. The receiver's name
    is captured but never constrained -- it is a per-file styling choice
    (app/router/server/fastify/...), not architectural evidence.

    Two independent steps (see docs/decisions/ROUTE_DISCOVERY_MULTILINE_DESIGN.md):
    find the call site with a narrow regex matching only
    `receiver.method(` (guaranteed to be on one line in practice), then
    read its arguments via the general-purpose, string-aware
    _extract_balanced()/_split_top_level() helpers -- which work
    identically whether the call spans one line or many. Replaces the
    prior approach, which matched the call AND its path with one
    single-line regex, and so silently missed any call formatted with the
    path argument on a following line (a common Prettier/Standard style;
    found via held-out testing to miss 0-100% of real routes in affected
    repositories, depending on formatting consistency).

    Comment-aware: file_text is passed through strip_comments() first, so a
    code-shaped example inside a // or /* */ comment is not mistaken for a
    real route registration (found via held-out testing)."""
    file_text = strip_comments(file_text)
    registrations = []
    for m in ROUTE_METHOD_RE.finditer(file_text):
        receiver, method = m.group(1), m.group(2)
        open_idx = m.end() - 1  # index of the call's opening '('
        call_args_text = _extract_balanced(file_text, open_idx, "(", ")")
        if call_args_text is None:
            continue  # unbalanced/truncated input -- no evidence, not a crash
        args = _split_top_level(call_args_text)
        if not args:
            continue
        path_match = _PATH_ARG_RE.fullmatch(args[0].strip())
        if not path_match:
            continue  # first argument isn't a `/`-prefixed string literal -- not a route call
        close_idx = open_idx + 1 + len(call_args_text)  # index of the matching ')'
        registrations.append({
            "receiver": receiver,
            "method": method.upper(),
            "path": path_match.group(1),
            "middleware_args": _middleware_args_from_call(args[1:]),
            "start_line": _line_number_at(file_text, m.start()),
            "end_line": _line_number_at(file_text, close_idx),
        })
    return registrations


# ---------------------------------------------------------------------------
# 3. Middleware / dependency discovery (new capability)
# ---------------------------------------------------------------------------

def _extract_balanced(text, open_idx, open_ch="{", close_ch="}"):
    """Returns the text strictly between the balanced open_ch/close_ch pair
    starting at open_idx (which must point at open_ch), respecting string/
    template-literal boundaries (a brace inside a string does not count).
    Returns None if the delimiter is never closed (malformed/truncated
    input) -- callers must treat that as 'no evidence', not a crash.

    General-purpose, delimiter-agnostic balance scanner -- not specific to
    object literals; used by the CommonJS object-literal export scan below,
    but not named or scoped to that one caller."""
    depth = 0
    i, n = open_idx, len(text)
    in_string = None
    content_start = open_idx + 1
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == in_string:
                in_string = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            in_string = ch
            i += 1
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[content_start:i]
        i += 1
    return None


def _split_top_level(text, sep=","):
    """Splits text on sep, but only at nesting depth 0 -- occurrences of sep
    inside (), [], {}, or a string/template literal do not split. Needed
    because an object-literal export's entries can themselves contain
    commas (nested objects, function values, default parameters)."""
    parts = []
    current = []
    depth = 0
    in_string = None
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_string:
            current.append(ch)
            if ch == "\\" and i + 1 < n:
                current.append(text[i + 1])
                i += 2
                continue
            if ch == in_string:
                in_string = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            in_string = ch
            current.append(ch)
            i += 1
            continue
        if ch in "([{":
            depth += 1
            current.append(ch)
            i += 1
            continue
        if ch in ")]}":
            depth -= 1
            current.append(ch)
            i += 1
            continue
        if ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    parts.append("".join(current))
    return parts


def _object_literal_export_names(obj_body):
    """Given the text strictly inside a `{ ... }` object literal, returns
    the set of statically-determinable property names it defines -- the
    general mechanism behind CommonJS's `module.exports = { a, b, c }`
    shorthand-export convention (found necessary via v7 held-out testing:
    a real repository's controller exported this way, and its handlers
    were never connected back to the routes that reference them).

    For each top-level, comma-separated entry:
      - `name` (shorthand property) -> exported as `name`.
      - `name: value` -> exported as `name` (the property KEY is what a
        consumer references, e.g. `controller.name`, regardless of what
        local identifier `value` happens to be).
      - `'name': value` / `"name": value` -> same, quotes stripped.
      - `...spread` -> skipped: a spread's contributed names are not
        statically knowable from this file alone.
      - `[computed]: value` -> skipped: not a static name.
      - anything else that isn't a bare identifier/quoted-string key ->
        skipped, rather than guessed.
    """
    names = set()
    for entry in _split_top_level(obj_body):
        entry = entry.strip()
        if not entry or entry.startswith("...") or entry.startswith("["):
            continue
        depth = 0
        colon_at = None
        for i, ch in enumerate(entry):
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == ":" and depth == 0:
                colon_at = i
                break
        key = entry[:colon_at] if colon_at is not None else entry
        key = key.strip()
        if len(key) >= 2 and key[0] == key[-1] and key[0] in ("'", '"'):
            key = key[1:-1]
        if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", key):
            names.add(key)
    return names


def find_exported_names(file_text):
    """Best-effort export-name extraction across common JS/CommonJS export
    forms. Regex-based, not a real parser. Comment-aware for the same
    reason as find_route_registrations() -- see its docstring."""
    file_text = strip_comments(file_text)
    names = set()
    for m in re.finditer(r"export\s+const\s+([A-Za-z_$][A-Za-z0-9_$]*)", file_text):
        names.add(m.group(1))
    for m in re.finditer(r"export\s+function\s+([A-Za-z_$][A-Za-z0-9_$]*)", file_text):
        names.add(m.group(1))
    for m in re.finditer(r"export\s+default\s+function\s+([A-Za-z_$][A-Za-z0-9_$]*)", file_text):
        names.add(m.group(1))
    for m in re.finditer(r"export\s*\{([^}]*)\}", file_text):
        for part in m.group(1).split(","):
            part = part.strip().split(" as ")[-1].strip()
            if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", part):
                names.add(part)
    for m in re.finditer(r"(?:module\.)?exports\.([A-Za-z_$][A-Za-z0-9_$]*)\s*=", file_text):
        names.add(m.group(1))
    # CommonJS object-literal export shorthand: `module.exports = { a, b }`
    # (and the equivalent bare `exports = { a, b }`, though a plain
    # reassignment of `exports` itself has no effect at runtime unless it's
    # actually `module.exports` -- included anyway since it's the same
    # syntactic shape and costs nothing extra to recognize as evidence).
    for m in re.finditer(r"(?:module\.)?exports\s*=\s*\{", file_text):
        open_idx = m.end() - 1
        obj_body = _extract_balanced(file_text, open_idx)
        if obj_body is not None:
            names.update(_object_literal_export_names(obj_body))
    return names


def _resolve_arg_to_export(arg, exported_names, whole_module_aliases=frozenset()):
    """Does this middleware-argument token depend on one of the changed
    file's exports? Three forms of evidence, all general:

      - exact match: `protect` used bare, where `protect` is exported
        directly (export const protect = ...).
      - root-identifier match: `controller.getUsers` used as a route
        handler, where `controller` is itself exported (export const
        controller = ...) and `getUsers` is a member of the value it
        holds. Class methods are never themselves module exports in
        JS/TS -- only the class/instance binding is -- so resolving the
        ROOT identifier of a dotted reference against the exported names
        is the general, correct mechanism, not a special case for any
        particular class shape. Found via held-out testing against a
        real repository using exactly this pattern.
      - property match: `authController.logout` used as a route handler,
        where `authController` is an arbitrary LOCAL alias for a
        whole-module import/require of the changed file (see
        _whole_module_import_aliases) and `logout` is itself one of the
        changed file's exported property names (the common CommonJS
        `module.exports = { logout, ... }` object-literal, or
        `exports.logout = ...`, convention). This is the reverse
        situation from the root-identifier case above: here the LOCAL
        name is arbitrary and the PROPERTY is the export. Found via
        held-out testing against a real repository using exactly this
        pattern. Gated on whole_module_aliases (rather than matching any
        `X.propertyName` in the codebase) so an unrelated file's
        similarly-named property is never mistaken for a dependency.

    Returns the matched exported name, or None.
    """
    if arg in exported_names:
        return arg
    if "." not in arg:
        return None
    root, prop = arg.split(".", 1)
    if root in exported_names:
        return root
    if root in whole_module_aliases and prop in exported_names:
        return prop
    return None


def _whole_module_import_aliases(file_text, changed_stub):
    """Local variable names in `file_text` bound to a WHOLE-MODULE
    import/require of the file identified by `changed_stub` (its basename
    without extension) -- as opposed to a named import of one specific
    export. Needed to safely resolve `X.propertyName` where `propertyName`
    is a CommonJS object-literal/property-assignment export of the changed
    file and `X` is an arbitrary local alias for the whole exports object
    (e.g. `const authController = require('../controllers/auth.controller')`),
    without matching some unrelated `X.propertyName` elsewhere that merely
    happens to share a property name.

    Recognizes `const/let/var NAME = require(<path>)`, `import NAME from
    <path>` (default import), and `import * as NAME from <path>`
    (namespace import). Deliberately excludes `import { a, b } from <path>`
    (named imports) -- those bind specific export names directly and are
    handled by the root-identifier match above instead, not this
    whole-module mechanism."""
    ext_group = "|".join(re.escape(e) for e in SOURCE_EXTENSIONS)
    path_pat = rf"""['"][^'"]*{re.escape(changed_stub)}({ext_group})?['"]"""
    aliases = set()
    for m in re.finditer(
        rf"(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*require\(\s*{path_pat}\s*\)",
        file_text,
    ):
        aliases.add(m.group(1))
    for m in re.finditer(rf"import\s+([A-Za-z_$][A-Za-z0-9_$]*)\s+from\s*{path_pat}", file_text):
        aliases.add(m.group(1))
    for m in re.finditer(rf"import\s*\*\s*as\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*from\s*{path_pat}", file_text):
        aliases.add(m.group(1))
    return aliases


def find_middleware_usages(repo, changed_path, changed_text):
    """Does the changed file export something used as a route-middleware
    argument (or, via property access, a route HANDLER -- see
    _resolve_arg_to_export) elsewhere in the repository? If so, those
    routes are impacted by this change even though the changed file
    defines no routes of its own. Generic mechanism -- not keyed to any
    specific filename or class shape."""
    exported = find_exported_names(changed_text)
    if not exported:
        return []
    changed_stub = os.path.splitext(os.path.basename(changed_path))[0]
    usages = []
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if not is_source_file(fn):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, repo).replace("\\", "/")
            if rel == changed_path:
                continue
            try:
                with open(full, "r", errors="ignore") as f:
                    text = strip_comments(f.read())
            except OSError:
                continue
            # Optional extension suffix generalized to any known source
            # extension (or none -- import specifiers commonly omit it,
            # e.g. `from "../middleware/authMiddleware"`), not just .js.
            ext_group = "|".join(re.escape(e) for e in SOURCE_EXTENSIONS)
            if not re.search(rf"""(from|require)\s*\(?['"][^'"]*{re.escape(changed_stub)}({ext_group})?['"]""", text):
                continue
            whole_module_aliases = _whole_module_import_aliases(text, changed_stub)
            for reg in find_route_registrations(text):
                matched = {}
                for arg in reg["middleware_args"]:
                    name = _resolve_arg_to_export(arg, exported, whole_module_aliases)
                    if name:
                        matched[name] = True
                if matched:
                    usages.append({"route": reg, "file": rel, "used_names": sorted(matched)})
    return usages


# ---------------------------------------------------------------------------
# 4. Mount-prefix composition (route-label composition milestone)
#
# find_route_registrations() reports a route's bare, in-file literal path
# only -- "/", "/emojis" -- with no awareness that the file defining it may
# itself be mounted under a prefix elsewhere (`app.use('/api/v1', api)`),
# possibly transitively (api/index.js mounted at /api/v1, itself mounting
# emojis.js at /emojis). Real pilot evidence: three distinct real routes
# collapsed to an identical "GET /" label, and the same root cause made a
# route's own real, passing test coverage invisible, because test-evidence
# matching searches for the route's (uncomposed) literal path -- see
# pilot/reports/2026-08-29-product-validation-pilot.md, Case 2.
#
# This reuses find_route_registrations()'s own building blocks
# (_extract_balanced/_split_top_level for call arguments, _PATH_ARG_RE and
# _IDENTIFIER_ARG_RE for argument shape) applied to receiver.use(prefix,
# target) instead of receiver.method(path, ...) -- not a new discovery
# technique, the same one aimed at a mount instead of a route. Resolving a
# mount's target to the file it refers to reuses the same "is this local
# name bound to a whole-module import of some file" question
# _whole_module_import_aliases() already answers for middleware
# arguments, generalized to any relative import target instead of one
# already-known changed file.
# ---------------------------------------------------------------------------

MOUNT_METHOD_RE = re.compile(r"\b(\w+)\.use\(")


def find_mount_registrations(file_text):
    """Finds receiver.use(prefix, target) calls -- a MOUNT, not a route:
    it registers everything beneath `prefix` on whatever router/middleware
    `target` refers to, rather than handling `prefix` itself. Only a
    `.use(` call whose FIRST argument is a `/`-prefixed string literal
    counts: a path-less `app.use(someMiddleware)` has no prefix to
    compose and is not treated as a mount. Remaining arguments are kept
    if they're bare-identifier/property-chain shaped (the same filter
    route middleware arguments use, via _middleware_args_from_call) --
    real code sometimes chains local middleware before the router
    (`app.use('/api', authGuard, apiRouter)`), so more than one
    candidate can come back; the caller tries each until one resolves.
    Comment-aware, like find_route_registrations()."""
    file_text = strip_comments(file_text)
    mounts = []
    for m in MOUNT_METHOD_RE.finditer(file_text):
        open_idx = m.end() - 1
        call_args_text = _extract_balanced(file_text, open_idx, "(", ")")
        if call_args_text is None:
            continue
        args = _split_top_level(call_args_text)
        if len(args) < 2:
            continue  # no path argument -- not a mount by this definition
        path_match = _PATH_ARG_RE.fullmatch(args[0].strip())
        if not path_match:
            continue
        candidates = _middleware_args_from_call(args[1:])
        if not candidates:
            continue
        mounts.append({"prefix": path_match.group(1), "candidates": candidates})
    return mounts


def _import_bindings(file_text):
    """Local variable names in `file_text` bound to a WHOLE-MODULE
    import/require of some file via a RELATIVE path (starting with `.`)
    -- generalizes _whole_module_import_aliases() (scoped to one
    already-known target file) to record every such binding, keyed by
    local name, since a mount's target can refer to any file, not one
    known in advance. Same three forms, same exclusion of named imports,
    for the same reason: only a whole-module binding tells us the local
    name IS a specific other file, rather than one of its exports."""
    file_text = strip_comments(file_text)
    bindings = {}
    for m in re.finditer(
        r"""(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*require\(\s*['"](\.[^'"]*)['"]\s*\)""",
        file_text,
    ):
        bindings[m.group(1)] = m.group(2)
    for m in re.finditer(
        r"""import\s+([A-Za-z_$][A-Za-z0-9_$]*)\s+from\s*['"](\.[^'"]*)['"]""",
        file_text,
    ):
        bindings[m.group(1)] = m.group(2)
    for m in re.finditer(
        r"""import\s*\*\s*as\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*from\s*['"](\.[^'"]*)['"]""",
        file_text,
    ):
        bindings[m.group(1)] = m.group(2)
    return bindings


def _resolve_relative_import_target(repo, from_file, specifier):
    """Resolves a relative import specifier (e.g. "./api/index.js",
    "../middleware/auth", "./auth.route") used in `from_file`
    (repo-relative) to an actual repo-relative file path, trying each
    known source extension and an index-file fallback for a
    directory-style import -- the two common ways a specifier omits
    detail present on disk. Returns None if nothing on disk matches;
    never guesses at a target.

    Deliberately does NOT use os.path.splitext() to decide whether the
    specifier "already has an extension": Express's own common
    `name.route.js`/`name.controller.js`/`name.service.js` file-naming
    convention means splitext("auth.route") returns ("auth", ".route"),
    which looks like it already has an extension and isn't one -- found
    via real-world verification against hagopj13/node-express-boilerplate,
    whose `require('./auth.route')` this would otherwise silently fail
    to resolve. is_source_file() checks against the actual known
    extension list instead."""
    base = os.path.normpath(os.path.join(os.path.dirname(from_file), specifier)).replace("\\", "/")
    if is_source_file(base) and os.path.isfile(os.path.join(repo, base)):
        return base
    candidates = [base + ext for ext in SOURCE_EXTENSIONS]
    candidates += [f"{base}/index{ext}" for ext in SOURCE_EXTENSIONS]
    for cand in candidates:
        if os.path.isfile(os.path.join(repo, cand)):
            return cand
    return None


def build_mount_map(repo):
    """Repo-wide: for every file mounted under a prefix by some OTHER
    file via receiver.use(prefix, target) -- where `target` resolves,
    through an ordinary relative import/require in the mounting file, to
    that file -- records {prefix, parent}. Walked once per analysis run
    (not once per changed file) and passed to compose_route_path().
    First mount found wins if a file is (unusually) mounted in more than
    one place; not otherwise disambiguated -- a disclosed simplification,
    not a silent one."""
    mounted_by = {}
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        for fn in sorted(filenames):
            if not is_source_file(fn):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, repo).replace("\\", "/")
            try:
                with open(full, "r", errors="ignore") as f:
                    text = f.read()
            except OSError:
                continue
            mounts = find_mount_registrations(text)
            if not mounts:
                continue
            bindings = _import_bindings(text)
            for mount in mounts:
                for candidate in mount["candidates"]:
                    root = candidate.split(".", 1)[0]
                    specifier = bindings.get(root)
                    if not specifier:
                        continue
                    target = _resolve_relative_import_target(repo, rel, specifier)
                    if not target or target == rel:
                        continue
                    if target not in mounted_by:
                        mounted_by[target] = {"prefix": mount["prefix"], "parent": rel}
                    break
    return mounted_by


_MAX_MOUNT_DEPTH = 25  # defensive cycle/depth guard, not a framework-specific limit


def effective_mount_prefix(mount_map, file_path):
    """Composes the full, externally-visible path prefix for `file_path`
    by walking its mount chain leaf-to-root: if some file mounts it under
    a prefix, and that mounting file is itself mounted elsewhere, and so
    on, transitively. Returns "" if the file isn't mounted anywhere --
    the common case, and exactly the existing behavior for a route
    registered directly (see compose_route_path()). Depth/cycle-guarded
    against malformed input, not a domain-specific limit."""
    prefix = ""
    current = file_path
    seen = set()
    depth = 0
    while current in mount_map and current not in seen and depth < _MAX_MOUNT_DEPTH:
        seen.add(current)
        entry = mount_map[current]
        prefix = entry["prefix"].rstrip("/") + prefix
        current = entry["parent"]
        depth += 1
    return re.sub(r"/+", "/", prefix) if prefix else ""


def compose_route_path(mount_map, file_path, literal_path):
    """The effective, externally-visible path for a route registered
    with `literal_path` in `file_path`: `literal_path` unchanged if the
    file isn't mounted anywhere (existing behavior, preserved exactly),
    otherwise the composed mount prefix concatenated with it (e.g.
    prefix "/api/v1" + path "/emojis" -> "/api/v1/emojis").

    A bare root path ("/") composes to the prefix itself, with no added
    trailing slash (prefix "/api/v1" + path "/" -> "/api/v1", not
    "/api/v1/") -- matching real Express mount semantics (mounting a
    router's own "/" at a prefix serves that prefix exactly, not
    prefix+"/"), and required for find_test_evidence()/find_callers()'s
    substring search to actually match a real test's request path
    (`.get("/api/v1")` never contains a trailing slash) -- confirmed
    against the real repository this milestone's fixture is modeled on."""
    prefix = effective_mount_prefix(mount_map, file_path)
    if not prefix:
        return literal_path
    if literal_path == "/":
        return prefix
    combined = prefix.rstrip("/") + literal_path
    return re.sub(r"/+", "/", combined)
