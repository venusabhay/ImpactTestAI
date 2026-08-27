# Architecture Discovery — Design (ADAPT_ARCHITECTURE_DISCOVERY)

Written before implementation, per the required process. This document proposes the discovery mechanism; it does not touch `design8.md`/`design9.md` (domain contracts and system architecture remain frozen) or the risk/decision policy in `analyze_change.py` (probability handling, `risk_level` computation, `ESCALATE`/`REQUIRE_ADDITIONAL_VALIDATION`/`ACCEPT` rules are out of scope and will not change).

## What's actually broken (from the Stage 2C report)

Two hardcoded assumptions, both specific to `social-media-mini`'s conventions:

1. `service_name_from_path()` matches only `services/([^/]+)/`.
2. `find_route_handlers()` matches only the literal receiver name `app`: `app\.(get|post|put|delete|patch)\(`.

A third issue is not a discovery gap but a truthfulness bug (explanatory text emitted for a check that never ran) — fixed separately in the same pass since it's directly implicated in the "dangerous confidence" finding, but it is a bug fix, not a discovery capability.

## Scope boundary (stated up front, not discovered later)

This design targets **Node.js repositories using Express-style HTTP frameworks** (Express itself, and anything using the same `receiver.method(path, ...middleware, handler)` calling convention — Fastify, Koa-with-router-adapters, etc., share enough surface syntax to be partially caught by the same pattern, though only Express has been verified). It does **not** attempt to discover architecture in other languages or frameworks (Python/Django/Flask, Java/Spring, Go, Ruby/Rails, etc.). A held-out repository outside this scope is expected to fail, and that failure is a valid, reportable result — not a bug to route around.

Within that boundary, the goal is to replace **hardcoded path/name assumptions** with **evidence discovered from the repository itself**: package manifests, import/export statements, and the actual syntax used to register routes and attach middleware — not naming conventions specific to any repository this tool has been shown so far.

## Proposed discovery primitives

### 1. Component discovery (replaces `services/<name>/` assumption)

**Evidence used:** the presence of a `package.json` file. Every directory containing one (excluding `node_modules`, `.git`, `coverage`, `dist`, `build`) is a **component root** — an independently manifested unit of code, regardless of where it sits in the directory tree or what its parent directory is named.

```
find_components(repo) -> [{ name, root_dir }, ...]
    name = package.json's "name" field if present, else the directory's own basename
```

**Attribution:** for any file, its component is the *nearest* (deepest) component root that is an ancestor of that file's path. This generalizes `services/auth-service/` (a component root two levels deep) and `user-management-api/` (a component root one level deep, directly at the repo root) with the same rule, and requires no assumption about a parent directory being named `services`.

**Known limitation, disclosed up front:** repositories that don't use per-component `package.json` files (a single root manifest for the whole repo, or a non-Node repo) will discover exactly one component (the repo root) or none. This is an honest "insufficient evidence" outcome, not a crash.

### 2. Route discovery (replaces `app\.(get|post|...)\(` assumption)

**Evidence used:** the general Express calling convention — *some identifier*, followed by `.get(`/`.post(`/`.put(`/`.delete(`/`.patch(`, whose first argument is a quoted string that looks like a URL path. The receiver identifier is captured but not constrained to a fixed name (`app`, `router`, `server`, or any other local variable name are all treated identically), because the receiver's name is a per-repository, per-file styling choice, not architectural evidence.

```
find_route_registrations(file_text) -> [{ receiver, method, path, middleware_args, start_line, end_line }, ...]
```

`middleware_args` captures any bare identifiers passed between the path and the final handler (Express's convention for attaching middleware inline: `router.get(path, middlewareFn, handler)`), reusing the same brace-matched span-detection already proven in the current implementation.

**Known limitation:** this is regex/text-based, not a real JavaScript parser. Route registrations built dynamically (e.g., via a loop, a config-driven router, or a framework with a fundamentally different registration style such as file-based routing) will not be found. This is disclosed rather than special-cased around.

### 3. Middleware/dependency discovery (new capability — did not exist before)

This directly targets the Change-A-shaped gap: a file (e.g., authentication middleware) that defines no routes of its own, but is *used by* routes defined elsewhere.

**Evidence used:** (a) the changed file's exported names (`export const X`, `export function X`, `export { X, Y }`, `module.exports.X =`, best-effort regex, not a full parser); (b) whether any of those names appear as a `middleware_args` entry in a route registration discovered anywhere else in the repository, in a file that imports the changed file (matched by module path, reusing the existing import-detection regex).

```
find_middleware_usages(repo, changed_file) -> [{ route, defining_file }, ...]
```

Where a match is found, the routes using that middleware become impact-analysis entries for the changed file — attributed generically as "used as middleware by route X in file Y," never by the specific file or route name being special-cased in code.

### 4. HTTP-call detection (frontend/backend dependency evidence)

Minor generalization of the existing "does this look like an HTTP call" check: expand beyond `axios|fetch\(` to also recognize `\.ajax\(` and `XMLHttpRequest` as call-shaped evidence. The underlying mechanism (literal-string search for the route path across the whole repository, already repo-wide and not scoped to a single "service") is unchanged and was already general — its failure in Stage 2C was a downstream consequence of (1) and (2) above, not a defect of its own, confirmed by re-tracing the Stage 2C code path.

## What does NOT change

- `RiskAssessment`'s fields, thresholds, and the "probability stays `UNKNOWN`" invariant.
- `ValidationDecision`'s selection logic and the "no validation → `ESCALATE`" default.
- `RISK_PATTERNS` and `SENSITIVE_PATH_HINTS` (already general — keyword/diff-based, not path- or repo-specific).
- The cross-service real-HTTP-test detection (`test_file_is_real_cross_service`) — already general.
- design8.md, design9.md.

## Explicit exclusions (things this design deliberately does not attempt)

- No support for non-Node ecosystems.
- No real AST/parser — regex-based discovery, with disclosed false-negative risk on dynamic/unconventional code.
- No attempt to resolve fully-mounted route paths (e.g., recognizing that `/refresh` registered in a router mounted at `/api/users` is really `/api/users/refresh`). Cross-file matching relies on substring containment of the literal registered path, which is what already made the frontend/backend match work once route detection itself succeeds — this is an existing, unchanged mechanism, not a new one.

## Validation plan

1. Implement against the two known repositories and the recorded acceptance criteria (Change A/B/C on `user-management-app`; the `/verify` regression on `social-media-mini`).
2. Add automated tests demonstrating component/route/middleware discovery on both known repositories' actual structure.
3. Freeze.
4. Run, unmodified, against repositories not consulted while building this design or its implementation.
5. Report successes and failures with equal rigor.
