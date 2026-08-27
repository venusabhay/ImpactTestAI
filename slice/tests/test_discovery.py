"""
Unit tests for slice/discovery.py -- the general-purpose, repository-agnostic
architecture-discovery primitives introduced for ADAPT_ARCHITECTURE_DISCOVERY.

Uses synthetic tmp_path fixtures, not the real social-media-mini or
user-management-app repositories (those are exercised by
test_known_repos_regression.py) -- these tests are about the mechanism
itself, independent of any specific repository.
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import discovery  # noqa: E402


# ---------------------------------------------------------------------------
# Component discovery
# ---------------------------------------------------------------------------

def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def test_finds_components_at_any_depth_not_just_services_prefix(tmp_path):
    # Deliberately NOT under a "services/" parent -- this is the exact case
    # user-management-app represents (components at repo root).
    _write(tmp_path / "backend-thing/package.json", json.dumps({"name": "backend-thing"}))
    _write(tmp_path / "frontend-thing/package.json", json.dumps({"name": "frontend-thing"}))
    # And a deeply nested one, mirroring social-media-mini's services/<name>/.
    _write(tmp_path / "apps/nested/deep/package.json", json.dumps({"name": "deep-svc"}))

    components = discovery.find_components(str(tmp_path))
    names = {c["name"] for c in components}
    assert names == {"backend-thing", "frontend-thing", "deep-svc"}


def test_component_uses_package_json_name_field_over_directory_name(tmp_path):
    _write(tmp_path / "some-dir/package.json", json.dumps({"name": "real-name"}))
    components = discovery.find_components(str(tmp_path))
    assert components[0]["name"] == "real-name"


def test_component_falls_back_to_directory_name_without_name_field(tmp_path):
    _write(tmp_path / "some-dir/package.json", "{}")
    components = discovery.find_components(str(tmp_path))
    assert components[0]["name"] == "some-dir"


def test_component_for_path_picks_deepest_ancestor(tmp_path):
    _write(tmp_path / "package.json", json.dumps({"name": "root"}))
    _write(tmp_path / "services/auth/package.json", json.dumps({"name": "auth"}))
    components = discovery.find_components(str(tmp_path))

    assert discovery.component_for_path("services/auth/server.js", components) == "auth"
    assert discovery.component_for_path("some/other/file.js", components) == "root"


def test_node_modules_excluded(tmp_path):
    _write(tmp_path / "real/package.json", json.dumps({"name": "real"}))
    _write(tmp_path / "real/node_modules/somedep/package.json", json.dumps({"name": "somedep"}))
    components = discovery.find_components(str(tmp_path))
    assert {c["name"] for c in components} == {"real"}


# ---------------------------------------------------------------------------
# Route discovery -- must work for ANY receiver name, not just "app"
# ---------------------------------------------------------------------------

def test_finds_routes_on_app_receiver():
    src = 'app.get("/health", (req, res) => { res.send("ok"); });\n'
    regs = discovery.find_route_registrations(src)
    assert len(regs) == 1
    assert regs[0]["receiver"] == "app"
    assert regs[0]["path"] == "/health"
    assert regs[0]["method"] == "GET"


def test_finds_routes_on_router_receiver():
    # This is exactly the pattern that broke on user-management-app.
    src = 'router.post("/register", async (req, res) => {\n  doStuff();\n});\n'
    regs = discovery.find_route_registrations(src)
    assert len(regs) == 1
    assert regs[0]["receiver"] == "router"
    assert regs[0]["path"] == "/register"
    assert regs[0]["method"] == "POST"


def test_finds_routes_on_arbitrary_receiver_name():
    src = 'myCustomRouterThing.delete("/widgets/:id", handler);\n'
    regs = discovery.find_route_registrations(src)
    assert len(regs) == 1
    assert regs[0]["receiver"] == "myCustomRouterThing"


def test_extracts_middleware_args_between_path_and_handler():
    src = 'router.get("/profile", protect, async (req, res) => {\n  res.json(req.user);\n});\n'
    regs = discovery.find_route_registrations(src)
    assert regs[0]["middleware_args"] == ["protect"]


def test_extracts_multiple_middleware_args():
    src = 'router.get("/", protect, authorize("admin"), async (req, res) => {\n});\n'
    regs = discovery.find_route_registrations(src)
    # authorize("admin") is a call, not a bare identifier -- only `protect`
    # should be captured as a plain middleware reference.
    assert "protect" in regs[0]["middleware_args"]


def test_end_line_matches_closing_brace():
    src = (
        'router.post("/verify", async (req, res) => {\n'
        "  step1();\n"
        "  if (x) {\n"
        "    step2();\n"
        "  }\n"
        "});\n"
    )
    regs = discovery.find_route_registrations(src)
    assert regs[0]["start_line"] == 1
    assert regs[0]["end_line"] == 6


# ---------------------------------------------------------------------------
# Exported-name discovery
# ---------------------------------------------------------------------------

def test_export_const():
    names = discovery.find_exported_names("export const protect = async (req, res, next) => {};\n")
    assert "protect" in names


def test_export_function():
    names = discovery.find_exported_names("export function authorize(role) { return () => {}; }\n")
    assert "authorize" in names


def test_export_brace_list():
    names = discovery.find_exported_names("const a = 1;\nexport { a, b as c };\n")
    assert names == {"a", "c"}


def test_module_exports_dot_assignment():
    names = discovery.find_exported_names("module.exports.protect = function() {};\n")
    assert "protect" in names


def test_no_exports_returns_empty_set():
    assert discovery.find_exported_names("const x = 1;\n") == set()


# ---------------------------------------------------------------------------
# Middleware/dependency discovery -- the new capability targeting the
# Change-A-shaped gap (a middleware file with no routes of its own).
# ---------------------------------------------------------------------------

def test_finds_middleware_usage_across_files(tmp_path):
    middleware_path = "middleware/auth.js"
    _write(tmp_path / middleware_path, "export const protect = async (req, res, next) => {};\n")
    _write(
        tmp_path / "routes/userRoutes.js",
        'import { protect } from "../middleware/auth.js";\n'
        'router.get("/profile", protect, async (req, res) => {\n  res.json(req.user);\n});\n',
    )
    with open(tmp_path / middleware_path) as f:
        changed_text = f.read()

    usages = discovery.find_middleware_usages(str(tmp_path), middleware_path, changed_text)
    assert len(usages) == 1
    assert usages[0]["route"]["path"] == "/profile"
    assert usages[0]["used_names"] == ["protect"]
    assert usages[0]["file"] == "routes/userRoutes.js"


def test_no_usage_found_when_not_imported(tmp_path):
    middleware_path = "middleware/auth.js"
    _write(tmp_path / middleware_path, "export const protect = async (req, res, next) => {};\n")
    _write(
        tmp_path / "routes/other.js",
        'router.get("/other", async (req, res) => {});\n',  # doesn't import auth.js at all
    )
    with open(tmp_path / middleware_path) as f:
        changed_text = f.read()

    usages = discovery.find_middleware_usages(str(tmp_path), middleware_path, changed_text)
    assert usages == []


def test_no_usage_when_file_exports_nothing():
    usages = discovery.find_middleware_usages("/nonexistent", "x.js", "const x = 1;\n")
    assert usages == []
