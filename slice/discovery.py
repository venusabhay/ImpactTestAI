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
        token = token.strip().strip("()")
        if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$.]*", token) and token not in ("async",):
            args.append(token)
    return args


def find_route_registrations(file_text):
    """Generalized route detection: ANY receiver.method(path, ...) call, not
    only app.method(...). The receiver's name is captured but never
    constrained -- it is a per-file styling choice (app/router/server/...),
    not architectural evidence."""
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

def find_exported_names(file_text):
    """Best-effort export-name extraction across common JS export forms.
    Regex-based, not a real parser."""
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
    return names


def find_middleware_usages(repo, changed_path, changed_text):
    """Does the changed file export something used as a route-middleware
    argument elsewhere in the repository? If so, those routes are impacted
    by this change even though the changed file defines no routes of its
    own. Generic mechanism -- not keyed to any specific filename."""
    exported = find_exported_names(changed_text)
    if not exported:
        return []
    changed_stub = os.path.splitext(os.path.basename(changed_path))[0]
    usages = []
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if not (fn.endswith(".js") or fn.endswith(".jsx")):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, repo).replace("\\", "/")
            if rel == changed_path:
                continue
            try:
                with open(full, "r", errors="ignore") as f:
                    text = f.read()
            except OSError:
                continue
            if not re.search(rf"""(from|require)\s*\(?['"][^'"]*{re.escape(changed_stub)}(\.js)?['"]""", text):
                continue
            for reg in find_route_registrations(text):
                used = exported & set(reg["middleware_args"])
                if used:
                    usages.append({"route": reg, "file": rel, "used_names": sorted(used)})
    return usages
