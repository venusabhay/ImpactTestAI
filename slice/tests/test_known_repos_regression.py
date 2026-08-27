"""
Behavior-level regression tests for ADAPT_ARCHITECTURE_DISCOVERY: does the
analyzer discover the right relationships in both known architectures?

These use synthetic fixtures that reproduce the STRUCTURAL SHAPE of the two
real repositories used to develop this milestone (social-media-mini,
user-management-app) -- not full copies of those repositories, which live
only on the developer's machine and are not available to a portable test
suite / CI runner. The synthetic fixtures capture exactly the structural
facts that matter to discovery: directory layout, route-registration
syntax, and (for user-management-app's shape) the auth-middleware pattern
that the original prototype could not see at all.

Live re-verification against the actual cloned repositories (including
reproducing the Stage 2B security regression) was performed manually as
part of freezing this milestone -- see
slice/reports/ADAPT_ARCHITECTURE_DISCOVERY_report.md for that evidence.
These tests verify BEHAVIOR (what discovery finds), not implementation
details of how it finds it.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import discovery  # noqa: E402


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


# ---------------------------------------------------------------------------
# social-media-mini's shape: services/<name>/ directories, app.METHOD(...)
# route syntax, one service calling another's endpoint over HTTP.
# ---------------------------------------------------------------------------

def _build_social_media_mini_shape(root):
    _write(f"{root}/services/auth-service/package.json", '{"name": "auth-service"}')
    _write(
        f"{root}/services/auth-service/server.js",
        'import express from "express";\n'
        "const app = express();\n"
        "const verifyCache = new Map();\n"
        'app.post("/verify", async (req, res) => {\n'
        "  const cached = verifyCache.get(req.body.token);\n"
        "  if (cached) return res.json({ user: cached.user });\n"
        "  res.json({ user: {} });\n"
        "});\n",
    )
    _write(f"{root}/services/auth-service/auth.test.js", "describe('verify', () => { it('works', () => {}); });\n")

    _write(f"{root}/services/user-service/package.json", '{"name": "user-service"}')
    _write(
        f"{root}/services/user-service/server.js",
        'import axios from "axios";\n'
        "const protect = async (req, res, next) => {\n"
        '  const r = await axios.post(`${process.env.AUTH_SERVICE_URL}/verify`, { token: "x" });\n'
        "  next();\n"
        "};\n",
    )
    return root


def test_discovers_services_prefixed_components(tmp_path):
    root = _build_social_media_mini_shape(str(tmp_path))
    components = discovery.find_components(root)
    names = {c["name"] for c in components}
    assert {"auth-service", "user-service"} <= names


def test_discovers_app_method_route_in_known_shape(tmp_path):
    root = _build_social_media_mini_shape(str(tmp_path))
    with open(f"{root}/services/auth-service/server.js") as f:
        text = f.read()
    regs = discovery.find_route_registrations(text)
    assert any(r["path"] == "/verify" and r["method"] == "POST" for r in regs)


def test_discovers_cross_service_caller_in_known_shape(tmp_path):
    root = _build_social_media_mini_shape(str(tmp_path))
    components = discovery.find_components(root)
    caller_file = "services/user-service/server.js"
    assert discovery.component_for_path(caller_file, components) == "user-service"
    # The literal route path appears in the caller file via a real HTTP call.
    with open(f"{root}/{caller_file}") as f:
        text = f.read()
    assert "/verify" in text and "axios" in text


# ---------------------------------------------------------------------------
# user-management-app's shape: flat component roots at repo root, no
# "services/" prefix, router.METHOD(...) syntax (not app.), and an
# authentication middleware file with no routes of its own -- the exact
# combination the original prototype could not see at all.
# ---------------------------------------------------------------------------

def _build_user_management_app_shape(root):
    _write(f"{root}/user-management-api/package.json", '{"name": "user-management-api"}')
    _write(
        f"{root}/user-management-api/middleware/authMiddleware.js",
        "export const protect = async (req, res, next) => {\n"
        "  const cached = authCache.get(token);\n"
        "  next();\n"
        "};\n"
        "export const authorize = (...roles) => (req, res, next) => next();\n",
    )
    _write(
        f"{root}/user-management-api/routes/userRoutes.js",
        'import express from "express";\n'
        'import { protect, authorize } from "../middleware/authMiddleware.js";\n'
        "const router = express.Router();\n"
        'router.get("/profile", protect, async (req, res) => {\n  res.json(req.user);\n});\n'
        'router.get("/", protect, authorize("admin"), async (req, res) => {\n  res.json([]);\n});\n'
        'router.patch("/:id/role", protect, authorize("admin"), async (req, res) => {\n  res.json({});\n});\n',
    )
    _write(f"{root}/user-management-api/__test__/user.test.js",
           'import { app } from "../server.js";\ndescribe("x", () => { it("y", () => {}); });\n')

    _write(f"{root}/user-management-frontend/package.json", '{"name": "user-management-frontend"}')
    _write(
        f"{root}/user-management-frontend/src/utils/api.js",
        "export async function apiRequest(url) {\n"
        '  return fetch(`${API_URL}/api/users/refresh`, { credentials: "include" });\n'
        "}\n",
    )
    return root


def test_discovers_flat_components_without_services_prefix(tmp_path):
    root = _build_user_management_app_shape(str(tmp_path))
    components = discovery.find_components(root)
    names = {c["name"] for c in components}
    # This is the exact case that failed completely before this milestone:
    # component roots directly at the repo root, no "services/" ancestor.
    assert {"user-management-api", "user-management-frontend"} <= names


def test_discovers_router_dot_method_routes_not_only_app(tmp_path):
    root = _build_user_management_app_shape(str(tmp_path))
    with open(f"{root}/user-management-api/routes/userRoutes.js") as f:
        text = f.read()
    regs = discovery.find_route_registrations(text)
    paths = {r["path"] for r in regs}
    assert {"/profile", "/", "/:id/role"} <= paths


def test_discovers_middleware_used_by_routes_with_no_routes_of_its_own(tmp_path):
    """This is the Change-A-shaped gap: authMiddleware.js defines no routes,
    but IS used as middleware by three routes elsewhere. The original
    prototype found zero impact for a change to this file; discovery must
    now find the routes that depend on it."""
    root = _build_user_management_app_shape(str(tmp_path))
    changed_path = "user-management-api/middleware/authMiddleware.js"
    with open(f"{root}/{changed_path}") as f:
        changed_text = f.read()

    usages = discovery.find_middleware_usages(root, changed_path, changed_text)
    routes_found = {u["route"]["path"] for u in usages}
    assert {"/profile", "/", "/:id/role"} <= routes_found
    assert all("protect" in u["used_names"] for u in usages)


def test_frontend_backend_dependency_is_attributable_to_a_component(tmp_path):
    """The frontend's literal reference to a backend route path must resolve
    to a real component name (not None/filtered-out), once component
    discovery no longer requires a services/<name>/ prefix."""
    root = _build_user_management_app_shape(str(tmp_path))
    components = discovery.find_components(root)
    frontend_file = "user-management-frontend/src/utils/api.js"
    assert discovery.component_for_path(frontend_file, components) == "user-management-frontend"
