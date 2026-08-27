"""
Architecture discovery primitives (ADAPT_ARCHITECTURE_DISCOVERY).

Replaces two hardcoded assumptions from the original prototype
(services/<name>/ directory layout, app.METHOD(...) route syntax) with
evidence-based discovery: component boundaries from package.json presence,
route registrations from the general receiver.method(path, ...) Express
calling convention (any receiver name), and a new capability -- middleware/
dependency discovery -- that finds files used as middleware by routes
defined elsewhere, via exported-name usage rather than a specific filename.

Scope boundary (see slice/ARCHITECTURE_DISCOVERY_DESIGN.md): Node.js
repositories using an Express-style calling convention. Regex/text-based,
not a real parser -- disclosed false-negative risk on dynamic or
unconventional route registration is expected and reported, not
special-cased around.

Contains NO reference to any specific repository, filename, or route path.
"""
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

ROUTE_CALL_RE = re.compile(r"\b(\w+)\.(get|post|put|delete|patch|all)\(\s*[\"'`](/[^\"'`]*)[\"'`]")

HANDLER_START_RE = re.compile(r"(async\s*\(|\([^)]*\)\s*=>|function\s*\(|=>\s*\{)")


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
# 2. Route discovery (generalizes app.METHOD(...) to any receiver)
# ---------------------------------------------------------------------------

def _extract_middleware_args(call_text, path):
    """Best-effort extraction of bare-identifier arguments between the route
    path and the final handler (Express's inline-middleware convention:
    receiver.method(path, middlewareFn, handler)). Regex-based heuristic,
    not a real parser -- see module docstring."""
    idx = call_text.find(path)
    if idx == -1:
        return []
    after = call_text[idx + len(path):]
    if after[:1] in "\"'`":
        after = after[1:]
    cut = HANDLER_START_RE.search(after)
    segment = after[:cut.start()] if cut else after
    args = []
    for token in segment.split(","):
        # Strips wrapping parens AND trailing statement punctuation (`;`)/
        # whitespace. Needed for the case with no inline-function handler at
        # all (e.g. `router.get(path, controller.method);`) -- there,
        # `segment` runs all the way to the end of the source line,
        # trailing semicolon included, since no HANDLER_START_RE match
        # exists to cut it off earlier. Without stripping `;` here, a bare
        # or dotted final-handler reference would never match the
        # identifier pattern below, and controller-method dependency
        # tracing could never fire for this (common) calling style.
        token = token.strip().strip("();").strip()
        if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$.]*", token) and token not in ("async",):
            args.append(token)
    return args


def find_route_registrations(file_text):
    """Generalized route detection: ANY receiver.method(path, ...) call, not
    only app.method(...). The receiver's name is captured but never
    constrained -- it is a per-file styling choice (app/router/server/...),
    not architectural evidence.

    Comment-aware: file_text is passed through strip_comments() first, so a
    code-shaped example inside a // or /* */ comment is not mistaken for a
    real route registration (found via held-out testing)."""
    file_text = strip_comments(file_text)
    lines = file_text.splitlines()
    registrations = []
    for i, line in enumerate(lines):
        m = ROUTE_CALL_RE.search(line)
        if not m:
            continue
        receiver, method, path = m.group(1), m.group(2), m.group(3)
        start_idx = m.start()
        depth = 0
        end_line = i
        started = False
        call_parts = []
        for j in range(i, len(lines)):
            segment = lines[j][start_idx:] if j == i else lines[j]
            call_parts.append(segment)
            for ch in segment:
                if ch == "(":
                    depth += 1
                    started = True
                elif ch == ")":
                    depth -= 1
            if started and depth <= 0:
                end_line = j
                break
        call_text = "\n".join(call_parts)
        registrations.append({
            "receiver": receiver,
            "method": method.upper(),
            "path": path,
            "middleware_args": _extract_middleware_args(call_text, path),
            "start_line": i + 1,
            "end_line": end_line + 1,
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
