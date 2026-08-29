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
# Formatting-independent (multiline) route span detection -- found necessary
# via v8 held-out testing: a route call whose path argument is on a
# following line from `receiver.method(` was never detected at all (0/9
# real routes in one held-out repository, 7/21 in another). General fix:
# find the call site with a narrow regex matching only `receiver.method(`,
# then read its arguments via the existing general-purpose
# _extract_balanced()/_split_top_level() helpers, which work identically
# regardless of line breaks. See docs/decisions/ROUTE_DISCOVERY_MULTILINE_DESIGN.md.
# ---------------------------------------------------------------------------

def test_single_line_route_still_detected():
    src = 'router.get("/users", handler);\n'
    regs = discovery.find_route_registrations(src)
    assert len(regs) == 1
    assert regs[0]["path"] == "/users"
    assert regs[0]["method"] == "GET"


def test_multiline_route_with_path_on_its_own_line():
    src = (
        "router.get(\n"
        '  "/users",\n'
        "  authMiddleware,\n"
        "  handler\n"
        ");\n"
    )
    regs = discovery.find_route_registrations(src)
    assert len(regs) == 1
    assert regs[0]["receiver"] == "router"
    assert regs[0]["method"] == "GET"
    assert regs[0]["path"] == "/users"
    assert regs[0]["middleware_args"] == ["authMiddleware", "handler"]
    assert regs[0]["start_line"] == 1
    assert regs[0]["end_line"] == 5


def test_multiline_route_matches_single_line_equivalent_exactly():
    """Multiline formatting must not change what is discovered -- same
    receiver, method, path, and middleware args as the single-line form."""
    single = 'router.get("/users", authMiddleware, handler);\n'
    multi = (
        "router.get(\n"
        '  "/users",\n'
        "  authMiddleware,\n"
        "  handler\n"
        ");\n"
    )
    reg_single = discovery.find_route_registrations(single)[0]
    reg_multi = discovery.find_route_registrations(multi)[0]
    for key in ("receiver", "method", "path", "middleware_args"):
        assert reg_single[key] == reg_multi[key]


def test_multiline_arguments_object_literal_kept_whole():
    """A config-object argument (e.g. Fastify's route-options convention)
    must not be split on its internal commas, and must not itself be
    mistaken for a middleware identifier."""
    src = (
        "fastify.get(\n"
        '  "/",\n'
        "  {\n"
        "    preHandler: [fastify.checkToken],\n"
        "    schema: getAllUsersSchema\n"
        "  },\n"
        "  async (_, reply) => {\n"
        "    return reply.send([]);\n"
        "  }\n"
        ");\n"
    )
    regs = discovery.find_route_registrations(src)
    assert len(regs) == 1
    assert regs[0]["path"] == "/"
    # The object literal isn't a bare/dotted identifier -- correctly excluded.
    assert regs[0]["middleware_args"] == []


def test_nested_parens_brackets_braces_inside_multiline_call():
    src = (
        "router.post(\n"
        '  "/widgets",\n'
        "  validate(schema({ strict: true, tags: [1, 2, (3 + 4)] })),\n"
        "  async (req, res) => {\n"
        "    if (req.body) {\n"
        "      doThing([1, 2, 3].map((x) => x + 1));\n"
        "    }\n"
        "  }\n"
        ");\n"
    )
    regs = discovery.find_route_registrations(src)
    assert len(regs) == 1
    assert regs[0]["path"] == "/widgets"
    # validate(...) is a call expression, not a bare identifier -- excluded.
    assert regs[0]["middleware_args"] == []
    assert regs[0]["end_line"] == 9


def test_multiple_routes_same_file_mixed_formatting():
    src = (
        'router.get("/a", handlerA);\n'
        "router.post(\n"
        '  "/b",\n'
        "  middlewareB,\n"
        "  handlerB\n"
        ");\n"
        'router.delete("/c", handlerC);\n'
    )
    regs = discovery.find_route_registrations(src)
    assert [(r["method"], r["path"]) for r in regs] == [
        ("GET", "/a"),
        ("POST", "/b"),
        ("DELETE", "/c"),
    ]
    assert regs[1]["middleware_args"] == ["middlewareB", "handlerB"]


def test_multiline_route_inside_comment_is_not_detected():
    src = (
        "// router.get(\n"
        '//   "/fake",\n'
        "//   handler\n"
        "// );\n"
        "const real = 1;\n"
    )
    assert discovery.find_route_registrations(src) == []


def test_multiline_route_with_string_containing_code_shaped_text():
    """A string literal that happens to contain route-call-shaped text must
    not be mistaken for arguments of the real call, and must not itself be
    misparsed as ending the balanced span early (e.g. via a stray `)` or
    `,` inside the string)."""
    src = (
        "router.post(\n"
        '  "/log",\n'
        "  async (req, res) => {\n"
        '    console.log("example: app.get(\\"/fake\\", handler)");\n'
        "    res.send({});\n"
        "  }\n"
        ");\n"
    )
    regs = discovery.find_route_registrations(src)
    assert len(regs) == 1
    assert regs[0]["path"] == "/log"
    assert regs[0]["end_line"] == 7


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


# ---------------------------------------------------------------------------
# TypeScript support (.ts/.tsx) -- found missing via held-out testing against
# a real TypeScript repository (ai-agents). Not a repository-specific fix:
# the same regexes, applied to a broader, generically-defined file-extension
# set (SOURCE_EXTENSIONS), covering any .ts/.tsx file in any repository.
# ---------------------------------------------------------------------------

def test_is_source_file_includes_ts_and_tsx():
    assert discovery.is_source_file("server.ts") is True
    assert discovery.is_source_file("Component.tsx") is True
    assert discovery.is_source_file("server.js") is True
    assert discovery.is_source_file("readme.md") is False


def test_strip_source_extension_handles_all_known_extensions():
    assert discovery.strip_source_extension("server.ts") == "server"
    assert discovery.strip_source_extension("Component.tsx") == "Component"
    assert discovery.strip_source_extension("server.js") == "server"
    assert discovery.strip_source_extension("noext") == "noext"


def test_component_discovery_finds_typescript_component(tmp_path):
    _write(tmp_path / "ts-service/package.json", '{"name": "ts-service"}')
    _write(
        tmp_path / "ts-service/server.ts",
        "import express from 'express';\n"
        "const app = express();\n"
        'app.post("/verify", async (req: Request, res: Response) => {\n  res.json({});\n});\n',
    )
    components = discovery.find_components(str(tmp_path))
    assert {"ts-service"} <= {c["name"] for c in components}


def test_route_registration_found_in_typescript_file_with_type_annotations():
    """Type annotations must not break the route-call regex -- it matches on
    the receiver.method(path, ...) shape, which TypeScript's syntax for this
    is a strict superset of."""
    src = 'router.post("/verify", async (req: Request, res: Response): Promise<void> => {\n  res.json({});\n});\n'
    regs = discovery.find_route_registrations(src)
    assert len(regs) == 1
    assert regs[0]["path"] == "/verify"


def test_middleware_usage_discovered_across_typescript_files(tmp_path):
    middleware_path = "middleware/auth.ts"
    _write(tmp_path / middleware_path,
           "export const protect = async (req: Request, res: Response, next: NextFunction): Promise<void> => {};\n")
    _write(
        tmp_path / "routes/userRoutes.tsx",
        'import { protect } from "../middleware/auth";\n'
        'router.get("/profile", protect, async (req: Request, res: Response) => {\n  res.json(req.user);\n});\n',
    )
    with open(tmp_path / middleware_path) as f:
        changed_text = f.read()

    usages = discovery.find_middleware_usages(str(tmp_path), middleware_path, changed_text)
    assert len(usages) == 1
    assert usages[0]["file"] == "routes/userRoutes.tsx"


# ---------------------------------------------------------------------------
# Comment-aware scanning -- found necessary via held-out testing: a
# code-shaped example inside a comment was matched as a real route
# registration. General fix (strip_comments), not tied to any repository.
# ---------------------------------------------------------------------------

def test_strip_comments_blanks_line_comment():
    src = '// app.get("/fake", handler);\nconst x = 1;\n'
    stripped = discovery.strip_comments(src)
    assert "app.get" not in stripped
    assert "const x = 1;" in stripped


def test_strip_comments_blanks_block_comment_preserving_line_count():
    src = '/* app.get("/fake", handler);\nmore comment */\nconst x = 1;\n'
    stripped = discovery.strip_comments(src)
    assert "app.get" not in stripped
    assert stripped.count("\n") == src.count("\n")  # line numbers unaffected


def test_strip_comments_does_not_touch_urls_inside_strings():
    src = 'const url = "http://example.com";\n'
    stripped = discovery.strip_comments(src)
    assert "http://example.com" in stripped


def test_route_inside_comment_is_not_detected():
    src = '// Example: app.get("/fake-example", handler);\nconst real = 1;\n'
    regs = discovery.find_route_registrations(src)
    assert regs == []


def test_route_inside_block_comment_is_not_detected():
    src = '/**\n * router.post("/also-fake", handler)\n */\nconst real = 1;\n'
    regs = discovery.find_route_registrations(src)
    assert regs == []


def test_real_route_after_comment_is_still_detected():
    src = '// a normal comment, no code here\napp.get("/real", handler);\n'
    regs = discovery.find_route_registrations(src)
    assert len(regs) == 1
    assert regs[0]["path"] == "/real"
    assert regs[0]["start_line"] == 2  # line number correctly unaffected by the comment above


def test_export_inside_comment_is_not_detected():
    src = '// export const fakeExport = 1;\nconst real = 2;\n'
    assert discovery.find_exported_names(src) == set()


# ---------------------------------------------------------------------------
# Controller-method dependency tracing -- found necessary via held-out
# testing against a real repository using class-based controllers, where
# route handlers are referenced as `controller.methodName` (property
# access), not a bare imported identifier. General fix: resolve the ROOT
# identifier of a dotted reference against the changed file's exports --
# class methods are never themselves module exports in JS/TS, only the
# class/instance binding is, so this is the correct general mechanism, not
# a special case for any specific class or file.
# ---------------------------------------------------------------------------

def test_controller_method_reference_resolves_to_its_export(tmp_path):
    controller_path = "controllers/userController.ts"
    _write(
        tmp_path / controller_path,
        "class UserController {\n"
        "  public getUsers = async (req, res) => { res.send([]); };\n"
        "}\n"
        "export const userController = new UserController();\n",
    )
    _write(
        tmp_path / "routes/userRouter.ts",
        'import { userController } from "../controllers/userController";\n'
        'userRouter.get("/", userController.getUsers);\n',
    )
    with open(tmp_path / controller_path) as f:
        changed_text = f.read()

    usages = discovery.find_middleware_usages(str(tmp_path), controller_path, changed_text)
    assert len(usages) == 1
    assert usages[0]["route"]["path"] == "/"
    assert usages[0]["used_names"] == ["userController"]


def test_controller_method_reference_with_second_route(tmp_path):
    """Mirrors the real repository pattern found in held-out testing: two
    routes, one with an extra validation call before the handler
    reference."""
    controller_path = "controllers/userController.ts"
    _write(tmp_path / controller_path, "export const userController = new UserController();\n")
    _write(
        tmp_path / "routes/userRouter.ts",
        'import { userController } from "../controllers/userController";\n'
        'userRouter.get("/", userController.getUsers);\n'
        'userRouter.get("/:id", validateRequest(GetUserSchema), userController.getUser);\n',
    )
    with open(tmp_path / controller_path) as f:
        changed_text = f.read()

    usages = discovery.find_middleware_usages(str(tmp_path), controller_path, changed_text)
    routes_found = {u["route"]["path"] for u in usages}
    assert {"/", "/:id"} <= routes_found


def test_bare_identifier_still_resolves_exactly_not_just_by_prefix():
    assert discovery._resolve_arg_to_export("protect", {"protect"}) == "protect"
    assert discovery._resolve_arg_to_export("userController.getUsers", {"userController"}) == "userController"
    assert discovery._resolve_arg_to_export("unrelatedThing", {"protect"}) is None
    assert discovery._resolve_arg_to_export("somethingElse.method", {"protect"}) is None


# ---------------------------------------------------------------------------
# CommonJS object-literal export shorthand (`module.exports = { a, b, c }`)
# -- found necessary via v7 held-out testing: a real repository's controller
# exports its handlers this way, and they were never connected back to the
# routes that reference them (`find_exported_names` only recognized ESM
# `export const/function/{}` forms and CommonJS `exports.X = ...` property
# assignment, not this equally-common CommonJS object-literal form).
# ---------------------------------------------------------------------------

def test_object_literal_export_shorthand_properties():
    src = (
        "const getUsers = async (req, res) => {};\n"
        "const createUser = async (req, res) => {};\n"
        "module.exports = {\n  getUsers,\n  createUser,\n};\n"
    )
    assert discovery.find_exported_names(src) == {"getUsers", "createUser"}


def test_object_literal_export_explicit_key_value():
    src = "function impl() {}\nmodule.exports = {\n  getUsers: impl,\n};\n"
    names = discovery.find_exported_names(src)
    assert "getUsers" in names
    assert "impl" not in names  # the KEY is the exported name, not the local value


def test_object_literal_export_ignores_spread_and_computed_keys():
    src = "const dyn = 'x';\nmodule.exports = {\n  ...base,\n  [dyn]: 1,\n  real,\n};\n"
    assert discovery.find_exported_names(src) == {"real"}


def test_object_literal_export_with_nested_braces_in_value():
    src = "module.exports = {\n  config: { retries: 3 },\n  getUsers,\n};\n"
    names = discovery.find_exported_names(src)
    assert "config" in names
    assert "getUsers" in names
    assert "retries" not in names  # nested object's keys are not top-level exports


def test_object_literal_export_quoted_key():
    src = 'module.exports = {\n  "getUsers": impl,\n};\n'
    assert discovery.find_exported_names(src) == {"getUsers"}


def test_object_literal_export_inside_comment_is_not_detected():
    src = "// module.exports = { fake };\nconst real = 1;\n"
    assert discovery.find_exported_names(src) == set()


def test_controller_object_literal_export_connects_to_route(tmp_path):
    """Mirrors the real repository pattern found in v7 held-out testing:
    a plain-CommonJS controller exporting its handlers via object-literal
    shorthand, referenced elsewhere as `authController.logout`."""
    controller_path = "controllers/auth.controller.js"
    _write(
        tmp_path / controller_path,
        "const logout = async (req, res) => { res.status(204).send(); };\n"
        "const login = async (req, res) => {};\n"
        "module.exports = {\n  login,\n  logout,\n};\n",
    )
    _write(
        tmp_path / "routes/auth.route.js",
        "const authController = require('../controllers/auth.controller');\n"
        "router.post('/logout', authController.logout);\n",
    )
    with open(tmp_path / controller_path) as f:
        changed_text = f.read()

    usages = discovery.find_middleware_usages(str(tmp_path), controller_path, changed_text)
    assert len(usages) == 1
    assert usages[0]["route"]["path"] == "/logout"
    assert usages[0]["used_names"] == ["logout"]


def test_split_top_level_respects_nested_brackets_and_strings():
    parts = discovery._split_top_level("a, {b: 1, c: 2}, 'x, y', [1, 2]")
    assert [p.strip() for p in parts] == ["a", "{b: 1, c: 2}", "'x, y'", "[1, 2]"]


def test_extract_balanced_handles_braces_inside_strings():
    text = 'module.exports = { msg: "a { b", real };'
    open_idx = text.index("{")
    body = discovery._extract_balanced(text, open_idx)
    assert body == ' msg: "a { b", real '


# ---------------------------------------------------------------------------
# Mount-prefix composition (route-label composition milestone) -- see
# pilot/reports/2026-08-29-product-validation-pilot.md, Case 2, and
# docs/decisions/PRODUCT_VALIDATION_GAP_DISPOSITION.md. Requirement 7
# (existing impact/test matching keeps working with the composed route)
# and the full regression fixture live in tests/test_analyze_change.py,
# alongside the analyze_change.py machinery they need.
# ---------------------------------------------------------------------------

def test_unmounted_file_route_path_is_unchanged(tmp_path):
    """Requirement 1: a route registered directly (its defining file is
    not mounted anywhere) is completely unaffected -- existing behavior,
    preserved exactly."""
    _write(tmp_path / "app.js", "app.get('/users', handler);\n")
    mount_map = discovery.build_mount_map(str(tmp_path))
    assert mount_map == {}
    assert discovery.compose_route_path(mount_map, "app.js", "/users") == "/users"


def test_root_route_composes_under_mount_without_added_trailing_slash(tmp_path):
    """Requirement 2: router.get("/", ...) mounted at /api/v1 composes
    to the prefix itself. No trailing slash is added for a root route --
    this matches real Express mount semantics (mounting a router's own
    "/" at a prefix serves that prefix exactly) and is required for
    find_test_evidence()/find_callers() to actually match a real test's
    request path, which never contains one."""
    _write(tmp_path / "app.js", "const api = require('./api.js');\napp.use('/api/v1', api);\n")
    _write(tmp_path / "api.js", "router.get('/', handler);\n")
    mount_map = discovery.build_mount_map(str(tmp_path))
    assert mount_map == {"api.js": {"prefix": "/api/v1", "parent": "app.js"}}
    assert discovery.compose_route_path(mount_map, "api.js", "/") == "/api/v1"


def test_non_root_route_composes_under_mount(tmp_path):
    """Requirement 3: router.get("/emojis", ...) mounted at /api/v1
    composes to /api/v1/emojis."""
    _write(tmp_path / "app.js", "const api = require('./api.js');\napp.use('/api/v1', api);\n")
    _write(tmp_path / "api.js", "router.get('/emojis', handler);\n")
    mount_map = discovery.build_mount_map(str(tmp_path))
    assert discovery.compose_route_path(mount_map, "api.js", "/emojis") == "/api/v1/emojis"


def test_multiple_routes_under_the_same_mount(tmp_path):
    """Requirement 4: several routes in the same mounted file each
    compose correctly against the same mount."""
    _write(tmp_path / "app.js", "const api = require('./api.js');\napp.use('/api/v1', api);\n")
    _write(
        tmp_path / "api.js",
        "router.get('/', handler);\n"
        "router.post('/widgets', create);\n"
        "router.delete('/widgets/:id', remove);\n",
    )
    mount_map = discovery.build_mount_map(str(tmp_path))
    with open(tmp_path / "api.js") as f:
        routes = discovery.find_route_registrations(f.read())
    composed = {r["method"]: discovery.compose_route_path(mount_map, "api.js", r["path"]) for r in routes}
    assert composed == {
        "GET": "/api/v1",
        "POST": "/api/v1/widgets",
        "DELETE": "/api/v1/widgets/:id",
    }


def test_nested_router_mounts_compose_transitively(tmp_path):
    """Requirement 5: nested router mounts -- emojis.js mounted at
    /emojis under api.js, which is itself mounted at /api/v1 under
    app.js. This is the exact real pilot shape (app.js -> api/index.js
    -> api/emojis.js)."""
    _write(tmp_path / "app.js", "const api = require('./api.js');\napp.use('/api/v1', api);\n")
    _write(
        tmp_path / "api.js",
        "const emojis = require('./emojis.js');\n"
        "router.get('/', handler);\n"
        "router.use('/emojis', emojis);\n",
    )
    _write(tmp_path / "emojis.js", "router.get('/', handler);\n")
    mount_map = discovery.build_mount_map(str(tmp_path))
    assert mount_map["emojis.js"] == {"prefix": "/emojis", "parent": "api.js"}
    assert mount_map["api.js"] == {"prefix": "/api/v1", "parent": "app.js"}
    assert discovery.compose_route_path(mount_map, "emojis.js", "/") == "/api/v1/emojis"


def test_mount_prefix_trailing_slash_normalizes_the_same_as_without(tmp_path):
    """Requirement 6: a mount prefix written with a trailing slash
    (app.use('/api/v1/', api)) composes identically to one without."""
    _write(tmp_path / "app.js", "const api = require('./api.js');\napp.use('/api/v1/', api);\n")
    _write(tmp_path / "api.js", "router.get('/emojis', handler);\n")
    mount_map = discovery.build_mount_map(str(tmp_path))
    assert discovery.compose_route_path(mount_map, "api.js", "/emojis") == "/api/v1/emojis"


def test_use_without_a_path_argument_is_not_treated_as_a_mount(tmp_path):
    """A path-less app.use(middleware) has no prefix to compose and must
    not be mistaken for a mount -- only receiver.use(pathString, target)
    counts."""
    _write(tmp_path / "app.js", "const api = require('./api.js');\napp.use(api);\n")
    _write(tmp_path / "api.js", "router.get('/', handler);\n")
    mount_map = discovery.build_mount_map(str(tmp_path))
    assert mount_map == {}


def test_mount_target_with_a_dotted_filename_convention_resolves(tmp_path):
    """Regression: Express's own common `name.route.js` naming convention
    (also `name.controller.js`, `name.service.js`, ...) means the
    specifier "./auth.route" looks, to a naive os.path.splitext() check,
    like it already has a real extension (".route") -- it doesn't. Found
    via real-world verification against
    hagopj13/node-express-boilerplate, where this silently broke
    resolution of `require('./auth.route')` before being fixed."""
    _write(tmp_path / "app.js", "const auth = require('./auth.route');\napp.use('/auth', auth);\n")
    _write(tmp_path / "auth.route.js", "router.post('/login', handler);\n")
    mount_map = discovery.build_mount_map(str(tmp_path))
    assert mount_map == {"auth.route.js": {"prefix": "/auth", "parent": "app.js"}}
    assert discovery.compose_route_path(mount_map, "auth.route.js", "/login") == "/auth/login"


def test_es_module_default_import_mount_is_resolved(tmp_path):
    """The real pilot repository uses ES module syntax (`import X from
    './y.js'`), not just CommonJS require() -- both must resolve a
    mount's target to the file it refers to."""
    _write(tmp_path / "app.js", "import api from './api.js';\napp.use('/api/v1', api);\n")
    _write(tmp_path / "api.js", "router.get('/', handler);\n")
    mount_map = discovery.build_mount_map(str(tmp_path))
    assert mount_map == {"api.js": {"prefix": "/api/v1", "parent": "app.js"}}


# ---------------------------------------------------------------------------
# Workspace-root detection (workspace-aware validation installation
# milestone) -- see docs/decisions/WORKSPACE_AWARE_INSTALL_DESIGN.md and
# pilot/reports/2026-08-29-product-validation-pilot.md, Case 3.
# ---------------------------------------------------------------------------

def test_no_workspace_field_at_all_is_not_treated_as_a_workspace(tmp_path):
    """Negative/safety case: an ordinary, non-workspace repository (no
    ancestor package.json declares "workspaces" at all) must not be
    incorrectly treated as one."""
    _write(tmp_path / "package.json", json.dumps({"name": "plain-app"}))
    _write(tmp_path / "component" / "package.json", json.dumps({"name": "component"}))
    assert discovery.find_workspace_root(str(tmp_path), "component") is None


def test_workspace_root_detected_via_exact_member_path(tmp_path):
    """Real shape: socketio/socket.io's own root package.json lists each
    member as an exact path, not a wildcard (e.g.
    "packages/socket.io-parser"), no glob at all."""
    _write(
        tmp_path / "package.json",
        json.dumps({"name": "monorepo", "workspaces": ["packages/socket.io-parser", "packages/other"]}),
    )
    _write(tmp_path / "packages" / "socket.io-parser" / "package.json", json.dumps({"name": "socket.io-parser"}))
    root = discovery.find_workspace_root(str(tmp_path), "packages/socket.io-parser")
    assert root == ""  # "" is the repo root itself


def test_workspace_root_detected_via_wildcard_pattern(tmp_path):
    _write(tmp_path / "package.json", json.dumps({"name": "monorepo", "workspaces": ["packages/*"]}))
    _write(tmp_path / "packages" / "widgets" / "package.json", json.dumps({"name": "widgets"}))
    assert discovery.find_workspace_root(str(tmp_path), "packages/widgets") == ""


def test_yarn_classic_object_form_workspaces_field_is_supported(tmp_path):
    _write(
        tmp_path / "package.json",
        json.dumps({"name": "monorepo", "workspaces": {"packages": ["packages/*"], "nohoist": ["**/react"]}}),
    )
    _write(tmp_path / "packages" / "widgets" / "package.json", json.dumps({"name": "widgets"}))
    assert discovery.find_workspace_root(str(tmp_path), "packages/widgets") == ""


def test_workspace_exists_but_does_not_declare_this_component(tmp_path):
    """Ambiguous/unsupported case: a workspace root exists, but its
    declared patterns don't actually list this component -- must not be
    guessed at as a member anyway."""
    _write(tmp_path / "package.json", json.dumps({"name": "monorepo", "workspaces": ["packages/*"]}))
    _write(tmp_path / "apps" / "standalone" / "package.json", json.dumps({"name": "standalone"}))
    assert discovery.find_workspace_root(str(tmp_path), "apps/standalone") is None


def test_wildcard_pattern_does_not_cross_a_path_segment(tmp_path):
    """"packages/*" must match exactly one path segment beneath
    packages/, not an arbitrary number the way Python's own fnmatch
    would let "*" cross "/"."""
    _write(tmp_path / "package.json", json.dumps({"name": "monorepo", "workspaces": ["packages/*"]}))
    _write(tmp_path / "packages" / "widgets" / "nested" / "package.json", json.dumps({"name": "nested"}))
    assert discovery.find_workspace_root(str(tmp_path), "packages/widgets/nested") is None


def test_repo_root_component_has_no_workspace_ancestor(tmp_path):
    """A component that IS the repo root has no ancestor to find --
    covered explicitly rather than relying on the walk to fail safely."""
    _write(tmp_path / "package.json", json.dumps({"name": "monorepo", "workspaces": ["packages/*"]}))
    assert discovery.find_workspace_root(str(tmp_path), "") is None


def test_intermediate_package_json_without_workspaces_field_is_skipped(tmp_path):
    """A component nested under an intermediate directory that has its
    OWN package.json (but no "workspaces" field -- the normal shape of
    an ordinary package) must not stop the walk before it reaches the
    real workspace root further up."""
    _write(
        tmp_path / "package.json",
        json.dumps({"name": "monorepo", "workspaces": ["groups/team-a/packages/*"]}),
    )
    _write(tmp_path / "groups" / "team-a" / "package.json", json.dumps({"name": "team-a", "private": True}))
    _write(
        tmp_path / "groups" / "team-a" / "packages" / "widgets" / "package.json",
        json.dumps({"name": "widgets"}),
    )
    root = discovery.find_workspace_root(str(tmp_path), "groups/team-a/packages/widgets")
    assert root == ""
