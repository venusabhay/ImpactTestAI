#!/usr/bin/env python3
"""
Vertical-slice implementation of the design8/design9 decision chain,
restricted to what a single repository can actually support:

    Change -> ImpactAssessment -> RiskAssessment -> ValidationDecision
           -> (real validation execution) -> Outcome -> Recommendation

Deliberate simplifications relative to the frozen design (documented, not
silently substituted -- see slice/README.md for the full list):

  - No graph database / evidence index / decision store. All objects are
    plain Python dicts, serialized to JSON for the audit record.
  - No Claim object with an aggregation function. Each piece of evidence
    is surfaced directly, with a qualitative confidence bucket
    (HIGH / MEDIUM / LOW) assigned by an explicit, inspectable rule --
    never a numeric score presented as precise.
  - RiskAssessment.business_impact / exposure are qualitative buckets
    derived from structural facts (how many other services depend on the
    changed endpoint, whether its name matches a sensitive pattern) --
    these are legitimate structural observations, not predictions.
  - RiskAssessment.probability is explicitly NOT estimated by this slice.
    Risk indicators found in the diff (e.g. "introduces caching") are
    evidence that a risk factor is present -- they are not evidence of
    "the probability of failure is HIGH". Until there is historical
    outcome data to calibrate against, probability is reported as
    UNKNOWN / INSUFFICIENT EVIDENCE, and the indicators are surfaced
    separately, by name, rather than folded into a probability bucket.
    (Corrected in POLICY_VERSION 2 -- v1 conflated the two.)
  - "DecisionContext" is approximated by recording the repo path, git
    ref, tool version, and POLICY_VERSION alongside the report --
    sufficient to say what rules produced a given decision and to
    reproduce it, not a general-purpose reproducibility service.
  - RiskPolicy is a single hardcoded, versioned threshold function
    (POLICY_VERSION below), not a configurable object -- there is
    exactly one policy and one organization in this slice.
  - Stage 2 adds ONE operational data source: this repository's own
    GitHub Actions run history (public REST API, no auth). It is kept as
    a clearly separate evidence category (see fetch_ci_history()) and is
    NOT wired into probability, risk_level, or the recommendation
    algorithm -- it is additive evidence for a human reader, exactly as
    directed. No second operational data source (production telemetry,
    incident systems) and no deployment are introduced at this stage.

This script only ever reads the target repository (and, for Stage 2, this
repository's public GitHub Actions history) and runs its own existing
`npm test`. It does not modify, commit, or push anything anywhere.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

import discovery

# Version of this script itself (the code/mechanics), distinct from
# POLICY_VERSION (the risk/validation rules it implements). Bump on any
# change to the analyzer's behavior, output shape, or CLI surface, so a
# report can always be traced to exactly which code produced it -- not
# just which rules. Independent axis from POLICY_VERSION: the same tool
# version can run under different policy versions and vice versa.
TOOL_VERSION = "0.6.0-pilot"

# Version of the rule-based risk/validation policy implemented below.
# Bump this whenever the rules in build_risk_assessment(), final_recommendation(),
# or their thresholds change, so a given report/audit record always states
# exactly which rules produced it -- the slice's stand-in for design8's
# DecisionContext.policy_version until a real policy service exists.
#   v1: probability was derived from a count of diff risk-pattern hits,
#       presenting a heuristic indicator count as if it were a calibrated
#       failure probability.
#   v2: probability is no longer estimated at all in repo-only mode --
#       reported as UNKNOWN / INSUFFICIENT EVIDENCE. Risk indicators are
#       surfaced separately and by name; they inform risk_level but are
#       never presented as a probability.
#   v3 (Stage 2): adds GitHub Actions CI run history as a second, clearly
#       separate evidence category (fetch_ci_history()). It reports what
#       was observed (runs examined, confirmed job failures for the
#       changed service, time window, limitations) and is surfaced in the
#       report and audit record. It does NOT feed into probability,
#       risk_level, or the recommendation algorithm -- those are computed
#       identically to v2. CI history is additive evidence for a human
#       reader, not an automatic risk multiplier.
#   v4 (Stage 2B): recognizes a real cross-service integration test (one
#       that spawns the changed service as a live process and drives it
#       over real HTTP via axios, as opposed to an in-process/mocked/
#       duplicated app -- see test_file_is_real_cross_service()) as its own
#       evidence category, CROSS_SERVICE_VALIDATION. When one exists for
#       the structural risk identified, build_validation_decision() selects
#       it (previously always rejected as "no such test exists"), and
#       evidence_confidence can reach HIGH (previously capped at MEDIUM).
#       This is a change to what counts as evidence, not to how probability
#       is estimated -- probability remains UNKNOWN per v2/v3.
#   v5 (ADAPT_ARCHITECTURE_DISCOVERY): replaces hardcoded services/<name>/
#       and app.METHOD()-only discovery with evidence-based discovery (see
#       discovery.py and slice/ARCHITECTURE_DISCOVERY_DESIGN.md): components
#       are discovered from package.json presence at any depth; routes are
#       discovered from any receiver.method(path, ...) call, not only
#       `app.`; a new evidence category (MIDDLEWARE_DEPENDENCY) finds files
#       used as middleware by routes defined elsewhere, via exported-name
#       usage rather than a specific filename. structural_exposure_score is
#       broadened to include routes reached via a discovered middleware
#       dependency, not only cross-component callers -- the SAME
#       bucket_from_score() thresholds and formula shape apply unchanged.
#       No change to probability handling (still UNKNOWN), risk_level
#       thresholds, or the ESCALATE/REQUIRE_ADDITIONAL_VALIDATION/ACCEPT
#       rules in final_recommendation().
#   v6 (ADAPT_ARCHITECTURE_DISCOVERY, held-out finding): extends source-file
#       scanning to .ts/.tsx (discovery.SOURCE_EXTENSIONS), previously
#       silently limited to .js/.jsx -- an inherited gap from the original
#       JS-only prototype, found by held-out testing against a real
#       TypeScript repository, not a deliberate scope decision. Same
#       route/export/import regexes, applied to a broader file set; no
#       change to any formula, threshold, or decision rule.
#   v7 (ADAPT_ARCHITECTURE_DISCOVERY, narrow follow-up milestone): fixes two
#       specific gaps found in the v6 held-out round, both general, neither
#       repository-specific: (1) route/export scanning is now comment-aware
#       (discovery.strip_comments()) -- a code-shaped example inside a
#       comment was previously matched as a real route registration; (2)
#       controller-method dependency tracing -- a route handler referenced
#       as `controller.methodName` (property access, common in class-based
#       controllers) now resolves against the controller's export the same
#       way a bare identifier does, via discovery._resolve_arg_to_export().
#       Also fixed the underlying _extract_middleware_args() bug that made
#       (2) impossible: trailing `;` after a bare/dotted final-handler
#       reference (no inline function, so no HANDLER_START_RE cut point)
#       was never stripped, so the token never matched the identifier
#       pattern at all. No change to any formula, threshold, or decision
#       rule; no change to RiskAssessment/probability/risk_level semantics.
#   v8 (ADAPT_ARCHITECTURE_DISCOVERY, narrow follow-up milestone): fixes the
#       one gap found in the v7 held-out round: find_exported_names() did
#       not recognize the CommonJS object-literal export shorthand
#       (`module.exports = { getUsers, createUser }` and the equivalent
#       explicit-key form `module.exports = { getUsers: impl }`), only ESM
#       `export const/function/{}` and CommonJS `exports.X = ...` property
#       assignment. Added via a general balanced-brace scan
#       (discovery._extract_balanced()) plus a top-level-comma-aware object-
#       literal entry parser (discovery._object_literal_export_names()) --
#       not a special case for any file, since it recognizes the syntactic
#       shape, not any particular property name. This also required a
#       companion resolution fix: previously, `_resolve_arg_to_export()`
#       only matched a dotted reference's ROOT identifier against the
#       exported names (correct for a named/aliased import of one specific
#       export, e.g. a class-instance singleton). The object-literal export
#       case is the mirror image -- the LOCAL variable is an arbitrary
#       alias for a whole-module `require(...)`, and the PROPERTY name is
#       the actual export -- so a new, gated property-match mode was added,
#       restricted to cases where the root is a whole-module import/require
#       alias of the changed file specifically
#       (discovery._whole_module_import_aliases()), not any `X.propertyName`
#       in the codebase, to avoid false positives from unrelated files that
#       happen to share a property name. No change to any formula,
#       threshold, or decision rule; no change to RiskAssessment/
#       probability/risk_level semantics.
POLICY_VERSION = "repo-plus-ci-plus-cross-service-plus-discovery-v8"

# Patterns that indicate a NEWLY INTRODUCED risk shape (new state, new
# timing behavior, destructive operations) -- deliberately excludes generic
# domain vocabulary like "token"/"password"/"jwt.verify" that would appear
# in any auth-related diff regardless of whether this specific change adds
# risk. Those are instead captured once via SENSITIVE_PATH_HINTS, so they
# aren't double-counted per occurrence.
RISK_PATTERNS = [
    (r"\bcache\b", "introduces or touches caching (statefulness / staleness risk)"),
    (r"\bnew Map\(|\bnew Set\(", "introduces new in-memory state"),
    (r"\bsetInterval\(|\bsetTimeout\(", "introduces timer-based / asynchronous behavior"),
    (r"\bprocess\.exit\(", "can terminate the process"),
    (r"\bDROP \b|\.deleteMany\(|\.deleteOne\(", "deletes data"),
]

SENSITIVE_PATH_HINTS = ["verify", "login", "register", "auth", "password", "token", "payment", "admin"]


def run(cmd, cwd=None, timeout=None):
    return subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout)


def git(repo, args, timeout=30):
    return run(f"git {args}", cwd=repo, timeout=timeout)


# ---------------------------------------------------------------------------
# 1. Change
# ---------------------------------------------------------------------------

def get_change(repo, ref):
    """Everything we can say about 'what changed' using only git."""
    files = git(repo, f"diff --name-only {ref}").stdout.strip().splitlines()
    files = [f for f in files if f]
    diff_text = git(repo, f"diff {ref}").stdout
    # -U0: zero context lines, so changed_line_ranges() reflects only lines
    # actually touched, not the +/-3 lines of surrounding context that a
    # normal diff includes (which would falsely implicate adjacent, untouched
    # handlers as "changed").
    diff_text_u0 = git(repo, f"diff -U0 {ref}").stdout
    stat = git(repo, f"diff --stat {ref}").stdout.strip()
    head = git(repo, "rev-parse HEAD").stdout.strip()
    return {
        "changed_files": files,
        "diff_text": diff_text,
        "diff_text_u0": diff_text_u0,
        "diff_stat": stat,
        "base_ref": ref,
        "repo_head": head,
    }


def changed_line_ranges(diff_text, path):
    """New-file line ranges touched by the diff, per file (from @@ hunks)."""
    ranges = {}
    current_file = None
    for line in diff_text.splitlines():
        m = re.match(r"^\+\+\+ b/(.+)$", line)
        if m:
            current_file = m.group(1)
            ranges.setdefault(current_file, [])
            continue
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if m and current_file:
            start = int(m.group(1))
            length = int(m.group(2) or 1)
            ranges[current_file].append((start, start + max(length, 1)))
    return ranges.get(path, [])


# ---------------------------------------------------------------------------
# 2. Impact Assessment (evidence-based, repo-only)
# ---------------------------------------------------------------------------

def grep_repo(repo, pattern, exclude_paths=()):
    exclude = " ".join(f"--exclude-dir={d}" for d in ["node_modules", "coverage", ".git", "dist", "build"])
    result = run(f"grep -rn -F {json.dumps(pattern)} {exclude} .", cwd=repo)
    hits = []
    for line in result.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        path, lineno, snippet = parts[0].lstrip("./"), parts[1], parts[2].strip()
        if path in exclude_paths:
            continue
        hits.append({"file": path, "line": int(lineno), "snippet": snippet})
    return hits


def find_callers(repo, route_path, own_file, components):
    # A path with no meaningful segment (e.g. the bare root route "/") is a
    # substring of nearly everything (every URL, every filesystem path in a
    # Dockerfile, etc.) -- literal substring search against it is unreliable
    # regardless of which repository this runs against. This is a general
    # robustness guard on the search mechanism, not a rule about any specific
    # route, file, or repository: any repo with a route this generic would
    # hit the same false-positive flood.
    if len(route_path.strip("/")) == 0:
        return []
    hits = grep_repo(repo, route_path, exclude_paths={own_file})
    callers = []
    for h in hits:
        # Slightly broadened per ARCHITECTURE_DISCOVERY_DESIGN.md #4: axios
        # and fetch( were already covered; .ajax( and XMLHttpRequest add
        # coverage for older/alternative HTTP-call styles without narrowing
        # or special-casing anything.
        looks_like_call = bool(re.search(r"axios|fetch\(|\.ajax\(|XMLHttpRequest", h["snippet"]))
        callers.append({**h, "looks_like_http_call": looks_like_call,
                         "calling_service": discovery.component_for_path(h["file"], components)})
    return callers


TEST_FILE_SUFFIXES = tuple(f".test{ext}" for ext in discovery.SOURCE_EXTENSIONS)


def find_test_evidence(repo, route_path):
    if len(route_path.strip("/")) == 0:
        return []
    hits = grep_repo(repo, route_path)
    return [h for h in hits if h["file"].endswith(TEST_FILE_SUFFIXES)]


def test_file_is_real_cross_service(repo, test_file):
    """Does this test file actually drive a live, separately-running instance
    of the service over real HTTP (spawns a child process AND makes real
    network calls via axios), as opposed to an in-process/mocked/duplicated
    app? This is a generic content signal, not tied to any specific
    filename -- it is what a genuine cross-service integration test looks
    like as distinct from a supertest-against-an-in-process-app unit test."""
    path = os.path.join(repo, test_file)
    if not os.path.exists(path):
        return False
    with open(path, "r", errors="ignore") as f:
        text = f.read()
    return ("axios" in text) and (re.search(r"child_process|\bspawn\(", text) is not None)


def test_file_imports_module(repo, test_file, module_basename):
    """Does the test file actually import the module it claims to test,
    or does it hand-duplicate its own app (a real, generically-detectable
    gap seen in this repository)?"""
    path = os.path.join(repo, test_file)
    if not os.path.exists(path):
        return None
    with open(path, "r", errors="ignore") as f:
        text = f.read()
    # \s* between (from|require) and the opening quote: ES module syntax
    # ("from './server.js'") always has a space there; require('./server')
    # does not. A prior version of this regex omitted \s* and silently
    # produced false negatives (reported "does not import" for a test file
    # that plainly does) -- caught by tests/test_analyze_change.py.
    return bool(re.search(rf"""(from|require)\s*\(?['"]\.?/?{re.escape(module_basename)}['"]""", text)) \
        or bool(re.search(rf"""(from|require)\s*\(?['"]\./{re.escape(discovery.strip_source_extension(module_basename))}['"]""", text))


def _impact_for_route(repo, components, route, defining_path, defining_service,
                       primary_entity, affected_entities, uncertainty_sources):
    """Shared TRANSITIVE / TEST_COVERAGE / CROSS_SERVICE_VALIDATION discovery
    for one impacted route, regardless of whether it was reached because the
    route itself changed (DIRECT) or because the changed file is used as
    middleware by this route (MIDDLEWARE_DEPENDENCY) -- the caller supplies
    `primary_entity` already tagged with the right impact_type."""
    affected_entities.append(primary_entity)

    callers = find_callers(repo, route["path"], own_file=defining_path, components=components)
    caller_services = sorted({c["calling_service"] for c in callers
                               if c["calling_service"] and c["calling_service"] != defining_service})
    for cs in caller_services:
        cs_hits = [c for c in callers if c["calling_service"] == cs]
        affected_entities.append({
            "entity": f"{cs} (via calls to {route['path']})",
            "impact_type": "TRANSITIVE",
            "confidence": "HIGH" if any(c["looks_like_http_call"] for c in cs_hits) else "MEDIUM",
            "evidence": [{
                "type": "STATIC_ANALYSIS",
                "description": f"{c['file']}:{c['line']} references \"{route['path']}\" "
                                f"{'in what looks like an HTTP call' if c['looks_like_http_call'] else '(reference found, call pattern not confirmed)'}.",
            } for c in cs_hits],
        })

    test_hits = find_test_evidence(repo, route["path"])
    same_service_tests = [t for t in test_hits
                           if discovery.component_for_path(t["file"], components) == defining_service]
    distinct_test_files = sorted({t["file"] for t in same_service_tests})
    if distinct_test_files:
        for test_file in distinct_test_files:
            file_hits = [t for t in same_service_tests if t["file"] == test_file]
            imports_module = test_file_imports_module(repo, test_file, os.path.basename(defining_path))
            is_real_cross_service = test_file_is_real_cross_service(repo, test_file)

            if is_real_cross_service:
                affected_entities.append({
                    "entity": f"Real cross-service validation: {test_file}",
                    "impact_type": "CROSS_SERVICE_VALIDATION",
                    "confidence": "HIGH",
                    "evidence": [{
                        "type": "TEST_EXECUTION",
                        "description": f"{t['file']}:{t['line']} references \"{route['path']}\".",
                    } for t in file_hits] + [{
                        "type": "STATIC_ANALYSIS",
                        "description": (
                            f"{test_file} spawns a real, separate process running the changed "
                            f"module and drives it over real HTTP (via axios), rather than an "
                            f"in-process or mocked app -- this is direct evidence the changed "
                            f"behavior can be, and is, exercised as dependent services actually "
                            f"call it."
                        ),
                    }],
                })
            else:
                affected_entities.append({
                    "entity": f"Existing test coverage: {test_file}",
                    "impact_type": "TEST_COVERAGE",
                    "confidence": "MEDIUM" if imports_module else "LOW",
                    "evidence": [{
                        "type": "TEST_EXECUTION",
                        "description": f"{t['file']}:{t['line']} references \"{route['path']}\".",
                    } for t in file_hits] + [{
                        "type": "STATIC_ANALYSIS",
                        "description": (
                            f"{test_file} DOES import/require the changed module directly."
                            if imports_module else
                            f"{test_file} does NOT import or require {os.path.basename(defining_path)} -- "
                            f"it appears to re-implement its own test version of the route(s) instead. "
                            f"A passing result here does not confirm the actual changed code path was exercised."
                        ),
                    }],
                })
    else:
        uncertainty_sources.append(
            f"No test file evidence found for {route['method']} {route['path']} in component "
            f"'{defining_service}'."
        )

    uncertainty_sources.append(
        f"Production call volume / exposure for {route['method']} {route['path']}: Unknown / insufficient "
        f"evidence (no production telemetry access in this slice)."
    )
    uncertainty_sources.append(
        f"Historical incident rate for this endpoint: Unknown / insufficient evidence "
        f"(no incident-system access in this slice)."
    )


def build_impact_assessment(repo, change, components):
    affected_entities = []
    uncertainty_sources = []

    for path in change["changed_files"]:
        full_path = os.path.join(repo, path)
        if not os.path.exists(full_path) or not discovery.is_source_file(path):
            continue
        with open(full_path, "r", errors="ignore") as f:
            file_text = f.read()

        service = discovery.component_for_path(path, components)
        touched_ranges = changed_line_ranges(change["diff_text_u0"], path)
        handlers = discovery.find_route_registrations(file_text)

        any_relationship_found = False

        for h in handlers:
            overlaps = any(not (h["end_line"] < s or h["start_line"] > e) for s, e in touched_ranges)
            if not overlaps:
                continue
            any_relationship_found = True
            primary_entity = {
                "entity": f"{service or path}: {h['method']} {h['path']}",
                "impact_type": "DIRECT",
                "confidence": "HIGH",  # directly observed in the diff + file
                "evidence": [{
                    "type": "SOURCE_CODE",
                    "description": f"{path}:{h['start_line']}-{h['end_line']} defines {h['method']} {h['path']}, "
                                    f"and the diff modifies lines within that handler.",
                }],
            }
            _impact_for_route(repo, components, h, path, service, primary_entity,
                               affected_entities, uncertainty_sources)

        # Middleware/dependency discovery (new capability): does this file
        # export something used as a route-middleware argument elsewhere in
        # the repository? Finds impact for files -- e.g. authentication
        # middleware -- that define no routes of their own. Not gated on
        # the diff touching a specific line within the file: a changed
        # middleware file is treated as impacting every route discovered to
        # use it, at whole-file granularity (see ARCHITECTURE_DISCOVERY_DESIGN.md
        # for why finer-grained overlap detection isn't attempted here).
        usages = discovery.find_middleware_usages(repo, path, file_text)
        seen_routes = set()
        for u in usages:
            route = u["route"]
            key = (u["file"], route["path"], route["method"])
            if key in seen_routes:
                continue
            seen_routes.add(key)
            any_relationship_found = True
            using_component = discovery.component_for_path(u["file"], components)
            primary_entity = {
                "entity": f"{using_component or u['file']}: {route['method']} {route['path']} "
                          f"(depends on {os.path.basename(path)} as middleware)",
                "impact_type": "MIDDLEWARE_DEPENDENCY",
                "confidence": "HIGH",
                "evidence": [{
                    "type": "SOURCE_CODE",
                    "description": f"{path} exports {', '.join(u['used_names'])}, used as middleware by "
                                    f"{route['method']} {route['path']} registered in {u['file']}:"
                                    f"{route['start_line']}-{route['end_line']}.",
                }],
            }
            _impact_for_route(repo, components, route, u["file"], using_component or service,
                               primary_entity, affected_entities, uncertainty_sources)

        if not any_relationship_found:
            uncertainty_sources.append(
                f"No route or middleware relationship was discovered for {path} -- this may be a file "
                f"outside this analyzer's discovery scope (see slice/ARCHITECTURE_DISCOVERY_DESIGN.md), "
                f"not necessarily a file with no real impact."
            )

    return {
        "affected_entities": affected_entities,
        "uncertainty_sources": sorted(set(uncertainty_sources)),
    }


# ---------------------------------------------------------------------------
# 3. Risk Assessment (qualitative, rule-based, confidence-decomposed)
# ---------------------------------------------------------------------------

def scan_risk_patterns(diff_text):
    hits = []
    for line in diff_text.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for pattern, reason in RISK_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                hits.append({"line": line.strip(), "reason": reason})
    return hits


def bucket_from_score(score, thresholds=(1, 2, 4)):
    if score >= thresholds[2]:
        return "CRITICAL"
    if score >= thresholds[1]:
        return "HIGH"
    if score >= thresholds[0]:
        return "MEDIUM"
    return "LOW"


def build_risk_assessment(change, impact):
    transitive = [e for e in impact["affected_entities"] if e["impact_type"] == "TRANSITIVE"]
    caller_services = sorted({e["entity"].split(" (via")[0] for e in transitive})

    # Broadened for ADAPT_ARCHITECTURE_DISCOVERY: "structural exposure" is
    # now the count of distinct additional things known to depend on the
    # change -- cross-component callers (as before) PLUS routes reached via
    # a newly-discovered middleware dependency (e.g. authentication
    # middleware used by several endpoints in the same component). Same
    # bucket_from_score() formula and thresholds as before; only the input
    # is broadened, per the evidence now available.
    middleware_entities = [e for e in impact["affected_entities"] if e["impact_type"] == "MIDDLEWARE_DEPENDENCY"]
    middleware_route_count = len({e["entity"] for e in middleware_entities})
    structural_exposure_score = len(caller_services) + middleware_route_count

    changed_paths = [e["entity"].split(": ", 1)[-1] for e in impact["affected_entities"]
                      if e["impact_type"] in ("DIRECT", "MIDDLEWARE_DEPENDENCY")]
    sensitive_name_hit = any(
        any(hint in p.lower() for hint in SENSITIVE_PATH_HINTS) for p in changed_paths
    )

    pattern_hits = scan_risk_patterns(change["diff_text"])
    # Renamed from the v1 "distinct_reasons" -> risk_indicators: these are
    # observed FACTORS present in the diff (e.g. "introduces caching"). They
    # are evidence that a risk factor exists, not a measurement of failure
    # probability -- v1's mistake was treating a count of these as if it
    # were a calibrated probability. See POLICY_VERSION note at top of file.
    risk_indicators = sorted({h["reason"] for h in pattern_hits})

    impact_score = structural_exposure_score + (1 if sensitive_name_hit else 0)
    business_impact = bucket_from_score(impact_score, thresholds=(1, 2, 4))

    exposure = "HIGH" if structural_exposure_score >= 2 else ("MEDIUM" if structural_exposure_score == 1 else "LOW")

    # PROBABILITY IS DELIBERATELY NOT ESTIMATED IN REPO-ONLY MODE.
    # This slice has no historical outcome data to calibrate a failure
    # probability against -- estimating one from indicator count alone
    # would be presenting a heuristic as a measurement. Report it as an
    # explicit unknown instead, per the business vision's principle that
    # absence of evidence must never be presented as evidence of safety
    # (or of danger, in the other direction).
    probability = "UNKNOWN"
    probability_reason = (
        "Not estimated: no historical outcome data is available in this slice to calibrate a failure "
        "probability against. The risk indicators below are evidence that certain risk factors are "
        "present -- they are not a measurement of how likely a failure is."
    )

    test_coverage_entities = [e for e in impact["affected_entities"] if e["impact_type"] == "TEST_COVERAGE"]
    cross_service_entities = [e for e in impact["affected_entities"] if e["impact_type"] == "CROSS_SERVICE_VALIDATION"]
    direct_test_coverage = any(e["confidence"] == "MEDIUM" for e in test_coverage_entities) or bool(cross_service_entities)
    has_cross_service_validation = bool(cross_service_entities)

    impact_confidence = "HIGH" if structural_exposure_score > 0 or changed_paths else "LOW"
    # Always LOW: there is no basis to be more confident than that about a
    # dimension (probability) this policy version explicitly declines to estimate.
    probability_confidence = "LOW"
    # HIGH specifically when a real cross-service test exists (the strongest
    # evidence this slice can produce -- exercises the actual dependency
    # relationship, not merely "imports the module"); MEDIUM for module-import
    # coverage alone; LOW otherwise.
    evidence_confidence = "HIGH" if has_cross_service_validation else ("MEDIUM" if direct_test_coverage else "LOW")

    confidences = [impact_confidence, probability_confidence, evidence_confidence]
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    overall_confidence = min(confidences, key=lambda c: order[c])  # conservative: weakest link

    # risk_level is now derived from business_impact + exposure + the
    # number of distinct risk indicators observed -- structural facts and
    # named indicators, never from the (unestimated) probability. Max
    # possible sum is 9 (3+3+3); thresholds require broad agreement across
    # all three dimensions before reaching CRITICAL.
    indicator_level = bucket_from_score(len(risk_indicators), thresholds=(1, 2, 4))
    dim_value = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    risk_level = bucket_from_score(
        dim_value[business_impact] + dim_value[exposure] + dim_value[indicator_level],
        thresholds=(3, 5, 7),
    )

    return {
        "probability": probability,
        "probability_reason": probability_reason,
        "risk_indicators": risk_indicators,
        "business_impact": business_impact,
        "exposure": exposure,
        "risk_level": risk_level,
        "confidence": {
            "impact_confidence": impact_confidence,
            "probability_confidence": probability_confidence,
            "evidence_confidence": evidence_confidence,
            "overall": overall_confidence,
        },
        "structural_exposure": {
            "caller_services": caller_services,
            "middleware_route_count": middleware_route_count,
            "score": structural_exposure_score,
        },
        "sensitive_name_hit": sensitive_name_hit,
        "risk_pattern_hits": pattern_hits,
        "direct_test_coverage": direct_test_coverage,
        "has_cross_service_validation": has_cross_service_validation,
        "policy_version": POLICY_VERSION,
    }


# ---------------------------------------------------------------------------
# 3B. Historical CI evidence (Stage 2's one operational data source)
#
# This is deliberately kept separate from build_risk_assessment(): it is
# additive evidence for a human reader, not an input to probability,
# risk_level, or the recommendation algorithm. See POLICY_VERSION v3 note.
# ---------------------------------------------------------------------------

def _gh_api_get(url, timeout=15):
    req = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": "impacttestai-vertical-slice"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def fetch_ci_history(github_repo, service, workflow_path=".github/workflows/ci.yml", per_page=100, timeout=15):
    """Fetch this repository's real GitHub Actions run history for the CI
    workflow, and extract job-level outcomes relevant to `service`.

    Never fabricates a result: on any network/API failure, or if no
    matching job is found, the record says so explicitly (UNKNOWN /
    insufficient evidence) rather than defaulting to "no history" (which
    would be indistinguishable from "we checked and it's clean").
    """
    record = {
        "available": False,
        "source": "GitHub Actions REST API (public, unauthenticated)",
        "repo": github_repo,
        "workflow_path": workflow_path,
        "runs_examined": 0,
        "window_start": None,
        "window_end": None,
        "service_job_pattern": service,
        "service_job_results": [],
        "service_failures": 0,
        "service_cancellations": 0,
        "service_successes": 0,
        "runs_with_unrelated_failures": 0,
        "historical_signal": "UNKNOWN / insufficient evidence",
        "limitations": [],
        "error": None,
    }
    try:
        runs_data = _gh_api_get(
            f"https://api.github.com/repos/{github_repo}/actions/runs?per_page={per_page}", timeout=timeout
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
        record["error"] = f"{type(e).__name__}: {e}"
        record["limitations"].append(
            "Could not reach the GitHub Actions API -- CI history is UNKNOWN, not assumed clean or absent."
        )
        return record

    runs = [
        r for r in runs_data.get("workflow_runs", [])
        if r.get("path") == workflow_path and r.get("status") == "completed"
    ]
    record["runs_examined"] = len(runs)
    if runs:
        record["window_start"] = min(r["created_at"] for r in runs)
        record["window_end"] = max(r["created_at"] for r in runs)

    used_fallback_matching = False
    for r in runs:
        try:
            jobs_data = _gh_api_get(r["url"] + "/jobs", timeout=timeout)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
            record["limitations"].append(f"Could not fetch job detail for run {r['id']}: {e}")
            continue

        jobs = jobs_data.get("jobs", [])
        # Prefer a job whose name signals it actually TESTS this service (matrix jobs are
        # commonly named e.g. "Test Microservices (auth-service)"), rather than any job
        # that merely mentions the service's name -- a "Docker Build Test (auth-service)"
        # job succeeding says nothing about test correctness and would otherwise get
        # conflated into the same count.
        test_named = [j for j in jobs if re.search(r"\btest\b", j.get("name", ""), re.IGNORECASE)
                      and re.search(rf"\b{re.escape(service)}\b", j.get("name", ""))
                      and "docker" not in j.get("name", "").lower()]
        matched = test_named if test_named else [
            j for j in jobs if re.search(rf"\b{re.escape(service)}\b", j.get("name", ""))
        ]
        if not test_named and matched:
            used_fallback_matching = True
        other_failures = [j for j in jobs if j.get("conclusion") == "failure" and j not in matched]
        if other_failures:
            record["runs_with_unrelated_failures"] += 1

        for j in matched:
            entry = {
                "run_id": r["id"], "created_at": r["created_at"],
                "job_name": j["name"], "conclusion": j["conclusion"], "html_url": r["html_url"],
            }
            record["service_job_results"].append(entry)
            if j["conclusion"] == "failure":
                record["service_failures"] += 1
            elif j["conclusion"] == "cancelled":
                record["service_cancellations"] += 1
            elif j["conclusion"] == "success":
                record["service_successes"] += 1

    record["available"] = True

    if not record["service_job_results"]:
        record["historical_signal"] = (
            "UNKNOWN / insufficient evidence -- no CI job matching this service's name was found in the "
            "examined history."
        )
    elif record["service_failures"] > 0:
        record["historical_signal"] = (
            f"This area has experienced {record['service_failures']} confirmed CI job failure(s) "
            f"(conclusion 'failure', distinct from jobs merely cancelled by a sibling failing) across "
            f"{len(record['service_job_results'])} relevant run(s) examined."
        )
    else:
        record["historical_signal"] = (
            f"No confirmed CI job failures specific to this service were found across "
            f"{len(record['service_job_results'])} relevant run(s) examined "
            f"({record['service_cancellations']} job(s) were CANCELLED because a different, unrelated job in "
            f"the same run failed -- that is not evidence against this service, and is not counted as a failure)."
        )

    if used_fallback_matching:
        record["limitations"].append(
            f"No job name specifically indicating a test run for '{service}' was found in at least one "
            f"examined run; some matched jobs may be non-test jobs (e.g. Docker builds) that merely mention "
            f"'{service}' by name."
        )
    record["limitations"].append(
        "A CI job failure, where one exists, does not confirm a production regression -- it may reflect a "
        "flaky test, a dependency/environment issue, or an unrelated CI configuration problem. This history "
        "does not distinguish those causes; a confirmed failure is evidence of past instability, not a "
        "measured probability of future failure."
    )
    record["limitations"].append(
        f"Only {record['runs_examined']} workflow run(s) on `{workflow_path}` were examined, spanning "
        f"{record['window_start']} to {record['window_end']} -- too small and too recent a sample to support "
        f"any calibrated statistic."
    )
    return record


# ---------------------------------------------------------------------------
# 4. Validation Decision + real execution
# ---------------------------------------------------------------------------

def build_validation_decision(repo, change, risk, components):
    # Components affected by the change: the ones the changed files belong
    # to, PLUS any component discovered as impacted via a middleware
    # dependency or a cross-component caller -- otherwise a change whose
    # only impact is "component X's route depends on this" would never get
    # component X's test suite considered.
    services = {discovery.component_for_path(p, components) for p in change["changed_files"]}
    services |= set(risk["structural_exposure"]["caller_services"])
    services = sorted(s for s in services if s)
    selected, rejected = [], []

    for svc in services:
        svc_dir_rel = discovery.component_root_dir(svc, components)
        svc_dir = os.path.join(repo, svc_dir_rel) if svc_dir_rel is not None else None
        pkg_path = os.path.join(svc_dir, "package.json") if svc_dir else None
        has_test_script = False
        if pkg_path and os.path.exists(pkg_path):
            with open(pkg_path) as f:
                pkg = json.load(f)
            has_test_script = "test" in pkg.get("scripts", {})
        if has_test_script:
            reason = (
                f"'{svc}' component's existing test suite is the best available real validation for this change "
                f"(exists, runs via 'npm test')."
            )
            if risk["has_cross_service_validation"]:
                reason += (" This component's test run ALSO includes a real cross-service integration test "
                           "(spawns the actual service as a live process, driven over real HTTP) -- see "
                           "the E2E_TEST entry below.")
            elif not risk["direct_test_coverage"]:
                reason += (" NOTE: repo-evidence indicates this suite does not import the changed module directly "
                            "(it re-implements its own routes for testing) -- treat a PASS here as a weak signal, "
                            "not confirmation that the changed code path was exercised.")
            selected.append({
                "type": "INTEGRATION_TEST",
                "target": svc,
                "target_dir": svc_dir_rel,
                "command": "npm test",
                "decision_reason": reason,
            })
        else:
            rejected.append({
                "type": "INTEGRATION_TEST",
                "target": svc,
                "decision_reason": f"No 'test' script found for component '{svc}' "
                                    f"({'no package.json test script' if svc_dir else 'component root could not be resolved'}).",
            })

    # The validation that would matter most: does a real cross-service test
    # exist for the structural risk identified above? Select it if so
    # (it runs as part of the 'npm test' invocation already selected above,
    # since it lives alongside the service's other tests); otherwise, keep
    # being explicit that this is a capability gap, not a silent omission.
    if risk["structural_exposure"]["caller_services"]:
        if risk["has_cross_service_validation"]:
            selected.append({
                "type": "E2E_TEST",
                "target": ", ".join(risk["structural_exposure"]["caller_services"]),
                "command": "(covered by the INTEGRATION_TEST run above)",
                "decision_reason": (
                    "A real cross-service integration test exists that spawns the actual changed service as "
                    "a live process and drives it over real HTTP exactly as "
                    f"{', '.join(risk['structural_exposure']['caller_services'])} do in production, directly "
                    "exercising the structural risk identified above. This closes what was previously a "
                    "reported capability gap."
                ),
            })
        else:
            rejected.append({
                "type": "E2E_TEST",
                "target": ", ".join(risk["structural_exposure"]["caller_services"]),
                "decision_reason": (
                    "A cross-service integration test that actually calls the live, changed endpoint from "
                    f"{', '.join(risk['structural_exposure']['caller_services'])} would directly validate the "
                    "structural risk identified above, but no such test exists in this repository. This is a "
                    "capability gap, not a validation that was run and passed."
                ),
            })

    return {"selected_validations": selected, "rejected_validations": rejected}


def run_validation(repo, node_bin_dir, selected, npm_install=False):
    outcomes = []
    env = os.environ.copy()
    if node_bin_dir:
        env["PATH"] = f"{node_bin_dir}:{env.get('PATH', '')}"
    # If node_bin_dir is empty, run with the inherited PATH as-is -- this is
    # the normal case on a clean machine or CI runner where `node`/`npm`
    # already resolve correctly. --node-bin exists for environments (like
    # the original developer's machine) where the default `node` on PATH is
    # broken and a specific install must be prepended.
    for v in selected:
        if v["type"] == "E2E_TEST":
            # Not independently executable: it's covered by the INTEGRATION_TEST
            # run for its owning service (the cross-service test file lives
            # alongside that service's other tests and runs as part of the same
            # 'npm test' invocation). Its result is reflected there.
            continue
        svc_dir = os.path.join(repo, v["target_dir"])
        if npm_install:
            # A fresh checkout (e.g. in CI) has no node_modules. This is an
            # execution-environment concern, not a decision-policy one --
            # it doesn't change what gets selected or how outcomes are
            # judged, only whether the command can run at all. Off by
            # default so Stage 1/2/2B's exact prior behavior (dependencies
            # installed manually beforehand) is unaffected.
            install = subprocess.run(
                "npm install", cwd=svc_dir, shell=True, capture_output=True, text=True, timeout=300, env=env,
            )
            if install.returncode != 0:
                outcomes.append({
                    "target": v["target"], "command": "npm install", "result": "INCONCLUSIVE",
                    "exit_code": install.returncode,
                    "stdout_tail": "\n".join(install.stdout.splitlines()[-25:]),
                    "stderr_tail": "\n".join(install.stderr.splitlines()[-25:]),
                    "classification": "INFRASTRUCTURE (dependency install failed)",
                })
                continue
        try:
            result = subprocess.run(
                v["command"], cwd=svc_dir, shell=True, capture_output=True, text=True, timeout=180, env=env,
            )
            passed = result.returncode == 0
            outcomes.append({
                "target": v["target"],
                "command": v["command"],
                "result": "PASSED" if passed else "FAILED",
                "exit_code": result.returncode,
                "stdout_tail": "\n".join(result.stdout.splitlines()[-25:]),
                "stderr_tail": "\n".join(result.stderr.splitlines()[-25:]),
                "classification": (
                    "N/A" if passed else
                    "Unknown / insufficient evidence -- requires human triage "
                    "(this tool does not auto-classify failure cause)"
                ),
            })
        except subprocess.TimeoutExpired:
            outcomes.append({
                "target": v["target"], "command": v["command"], "result": "INCONCLUSIVE",
                "exit_code": None, "stdout_tail": "", "stderr_tail": "timed out",
                "classification": "INFRASTRUCTURE (timeout)",
            })
    return outcomes


# ---------------------------------------------------------------------------
# 5. Final recommendation
# ---------------------------------------------------------------------------

def final_recommendation(risk, outcomes, validation_decision):
    any_failed = any(o["result"] == "FAILED" for o in outcomes)
    any_inconclusive = any(o["result"] == "INCONCLUSIVE" for o in outcomes)
    no_validation_ran = len(outcomes) == 0

    if any_failed:
        return "ESCALATE", "At least one selected validation failed. Do not proceed without human review."
    if any_inconclusive or no_validation_ran:
        return "ESCALATE", "Validation could not be completed (infrastructure/timeout or none available). Escalate for human review."
    if risk["risk_level"] in ("HIGH", "CRITICAL") and not risk["direct_test_coverage"]:
        return ("REQUIRE_ADDITIONAL_VALIDATION",
                f"Risk is {risk['risk_level']} and the only available automated validation does not directly "
                f"exercise the changed code path. Require additional (likely manual or cross-service) validation "
                f"before proceeding.")
    if risk["confidence"]["overall"] == "LOW":
        return ("REQUIRE_ADDITIONAL_VALIDATION",
                "Overall confidence in this assessment is LOW. Proceeding on a low-confidence assessment is not "
                "recommended regardless of the risk bucket.")
    return "ACCEPT", "Selected validation passed, risk and confidence are within acceptable bounds for this slice's policy."


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_report(change, impact, risk, validation_decision, outcomes, recommendation, repo, node_bin_dir, ci_history=None):
    decision, decision_reason = recommendation
    direct = [e for e in impact["affected_entities"] if e["impact_type"] == "DIRECT"]
    transitive = [e for e in impact["affected_entities"] if e["impact_type"] == "TRANSITIVE"]
    middleware_dep = [e for e in impact["affected_entities"] if e["impact_type"] == "MIDDLEWARE_DEPENDENCY"]
    test_cov = [e for e in impact["affected_entities"] if e["impact_type"] == "TEST_COVERAGE"]
    cross_service_cov = [e for e in impact["affected_entities"] if e["impact_type"] == "CROSS_SERVICE_VALIDATION"]

    lines = []
    lines.append("# Change Risk & Validation Report\n")
    lines.append(f"*Generated {datetime.now(timezone.utc).isoformat()}Z from repository at `{repo}`, "
                  f"comparing working tree against `{change['base_ref']}` (HEAD `{change['repo_head'][:10]}`).*\n")

    lines.append("## CHANGE\n")
    direct_desc = "; ".join(e["entity"] for e in direct) or None
    if not direct_desc and middleware_dep:
        direct_desc = "; ".join(e["entity"] for e in middleware_dep)
    lines.append(f"{direct_desc or 'no route-level change detected'}.\n")
    lines.append(f"```\n{change['diff_stat']}\n```\n")

    lines.append("## POTENTIAL IMPACT\n")
    for e in direct:
        lines.append(f"- **{e['entity']}** (direct) -- confidence: {e['confidence']}")
    for e in middleware_dep:
        lines.append(f"- **{e['entity']}** (via middleware dependency) -- confidence: {e['confidence']}")
    for e in transitive:
        lines.append(f"- **{e['entity']}** (transitive) -- confidence: {e['confidence']}")
    lines.append("")

    lines.append("## EVIDENCE\n")
    for e in direct + middleware_dep + transitive + test_cov + cross_service_cov:
        for ev in e["evidence"]:
            lines.append(f"- [{ev['type']}] {ev['description']}")
    lines.append("")

    lines.append("## RISK\n")
    lines.append(f"**{risk['risk_level']}**  (business impact: {risk['business_impact']}, exposure: {risk['exposure']})\n")
    lines.append(f"Probability: **{risk['probability']}** -- {risk['probability_reason']}\n")
    lines.append(f"Confidence: **{risk['confidence']['overall']}** "
                 f"(impact: {risk['confidence']['impact_confidence']}, "
                 f"probability: {risk['confidence']['probability_confidence']}, "
                 f"evidence: {risk['confidence']['evidence_confidence']})\n")
    if risk["risk_indicators"]:
        lines.append("Risk indicators observed (factors present -- not a probability):")
        for ind in risk["risk_indicators"]:
            lines.append(f"- {ind}")
        lines.append("")

    lines.append("## HISTORICAL EVIDENCE (CI)\n")
    if not ci_history:
        lines.append("Not collected for this run (no `--github-repo` provided). This is a separate, optional "
                      "evidence source -- its absence does not affect the risk assessment above.\n")
    else:
        for svc, hist in ci_history.items():
            lines.append(f"**{svc}**\n")
            if not hist["available"]:
                lines.append(f"- CI history: **UNKNOWN / insufficient evidence** ({hist['error']})\n")
                continue
            lines.append(f"- Source: {hist['source']} (`{hist['repo']}`, workflow `{hist['workflow_path']}`)")
            lines.append(f"- Runs examined: {hist['runs_examined']} "
                         f"(window: {hist['window_start']} to {hist['window_end']})")
            lines.append(f"- Relevant job history for `{svc}`: {len(hist['service_job_results'])} run(s) matched -- "
                         f"{hist['service_failures']} failed, {hist['service_cancellations']} cancelled "
                         f"(due to an unrelated sibling job, not this service), {hist['service_successes']} passed")
            lines.append(f"- **Historical signal:** {hist['historical_signal']}")
            lines.append("- What this does NOT establish:")
            for lim in hist["limitations"]:
                lines.append(f"  - {lim}")
            lines.append("")

    lines.append("## WHY\n")
    why = []
    if risk["structural_exposure"]["caller_services"]:
        why.append(f"The changed endpoint is called by {len(risk['structural_exposure']['caller_services'])} "
                    f"other component(s): {', '.join(risk['structural_exposure']['caller_services'])}.")
    if risk["structural_exposure"]["middleware_route_count"]:
        why.append(f"The change is used as middleware by {risk['structural_exposure']['middleware_route_count']} "
                    f"distinct route(s) elsewhere in the codebase, discovered via export/import and "
                    f"route-registration analysis (see POTENTIAL IMPACT).")
    if risk["sensitive_name_hit"]:
        why.append("The changed route's name/path matches a security-sensitive pattern (auth/token/password/etc.).")
    if risk["risk_indicators"]:
        why.append("The diff contains factors associated with elevated risk: " + "; ".join(risk["risk_indicators"]) +
                    ". These are indicators the risk level accounts for, not a measured probability of failure.")
    if ci_history:
        for svc, hist in ci_history.items():
            if hist["available"]:
                why.append(f"CI history for {svc}: {hist['historical_signal']}")
    if not risk["direct_test_coverage"]:
        why.append("The relevant existing test file does not import the changed module -- it duplicates the route "
                    "logic instead, so passing tests are a weak, indirect signal at best.")
    why.append("Production usage frequency and historical incident rate for this endpoint are unknown -- "
                "this assessment is based on repository evidence only.")
    lines.append(" ".join(why) + "\n")

    lines.append("## RECOMMENDED VALIDATION\n")
    for v in validation_decision["selected_validations"]:
        lines.append(f"- RUN: `{v['command']}` in `{v['target']}` -- {v['decision_reason']}")
    for v in validation_decision["rejected_validations"]:
        lines.append(f"- NOT AVAILABLE: {v['type']} for `{v['target']}` -- {v['decision_reason']}")
    lines.append("")

    lines.append("## VALIDATION RESULT\n")
    if not outcomes:
        lines.append("No validation was executed.\n")
    for o in outcomes:
        lines.append(f"- `{o['command']}` in `{o['target']}`: **{o['result']}** (exit code {o['exit_code']})")
        lines.append(f"  - classification: {o['classification']}")
    lines.append("")
    for o in outcomes:
        lines.append(f"<details><summary>{o['target']} test output (tail)</summary>\n\n```\n{o['stdout_tail']}\n{o['stderr_tail']}\n```\n</details>\n")

    lines.append("## DECISION\n")
    lines.append(f"**{decision}**\n\n{decision_reason}\n")

    lines.append("## IMPORTANT UNKNOWNS\n")
    for u in impact["uncertainty_sources"]:
        lines.append(f"- {u}")
    lines.append("")

    lines.append(f"---\n*Tool version: `{TOOL_VERSION}`. Risk/validation rules: `{risk['policy_version']}`. "
                  f"Re-running this analysis with the same tool and policy version against the same repo "
                  f"state and ref should reproduce this exact assessment.*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Vertical-slice change-risk analyzer (design8/9 slice).")
    parser.add_argument("--version", action="version", version=f"tool={TOOL_VERSION} policy={POLICY_VERSION}")
    parser.add_argument("repo", help="Path to the target repository")
    parser.add_argument("--against", default="HEAD", help="Git ref to diff the working tree against")
    parser.add_argument("--node-bin", default=os.environ.get("NODE_BIN_DIR", ""),
                         help="Directory containing a working node/npm binary")
    parser.add_argument("--no-run", action="store_true", help="Skip actually executing validation")
    parser.add_argument("--out", default=None, help="Output report path (markdown)")
    parser.add_argument("--github-repo", default=None,
                         help="owner/repo on GitHub to pull CI run history from (Stage 2). Omit to skip.")
    parser.add_argument("--no-ci-history", action="store_true",
                         help="Skip fetching CI history even if --github-repo is given.")
    parser.add_argument("--npm-install", action="store_true",
                         help="Run 'npm install' before each selected validation (for a fresh checkout, e.g. in CI). "
                              "Off by default to preserve prior Stage 1/2/2B behavior exactly.")
    args = parser.parse_args()

    repo = os.path.abspath(args.repo)
    change = get_change(repo, args.against)
    if not change["changed_files"]:
        print("No changes found against", args.against, file=sys.stderr)
        sys.exit(1)

    # Discovered once per run: every package.json-rooted component in the
    # repository. See discovery.py / ARCHITECTURE_DISCOVERY_DESIGN.md --
    # replaces the prior hardcoded services/<name>/ assumption.
    components = discovery.find_components(repo)

    impact = build_impact_assessment(repo, change, components)
    risk = build_risk_assessment(change, impact)
    validation_decision = build_validation_decision(repo, change, risk, components)

    ci_history = {}
    if args.github_repo and not args.no_ci_history:
        services = sorted({discovery.component_for_path(p, components) for p in change["changed_files"]
                            if discovery.component_for_path(p, components)})
        for svc in services:
            print(f"Fetching CI history for service '{svc}' from {args.github_repo}...", file=sys.stderr)
            ci_history[svc] = fetch_ci_history(args.github_repo, svc)

    outcomes = []
    if not args.no_run and validation_decision["selected_validations"]:
        # --node-bin is optional: if omitted, run_validation() uses the
        # inherited PATH as-is, which is correct on a clean machine or CI
        # runner. Only pass --node-bin when the default `node` on PATH is
        # broken or absent.
        outcomes = run_validation(repo, args.node_bin, validation_decision["selected_validations"], args.npm_install)

    recommendation = final_recommendation(risk, outcomes, validation_decision)

    report = render_report(change, impact, risk, validation_decision, outcomes, recommendation, repo,
                            args.node_bin, ci_history)

    audit_record = {
        "repo": repo, "base_ref": args.against, "repo_head": change["repo_head"],
        "tool_version": TOOL_VERSION,
        "policy_version": POLICY_VERSION,
        "discovered_components": components,
        "changed_files": change["changed_files"],
        "impact": impact, "risk": risk, "validation_decision": validation_decision,
        "ci_history": ci_history,
        "outcomes": outcomes, "recommendation": {"decision": recommendation[0], "reason": recommendation[1]},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    out_path = args.out or "report.md"
    with open(out_path, "w") as f:
        f.write(report)
    with open(out_path.replace(".md", ".audit.json"), "w") as f:
        json.dump(audit_record, f, indent=2)

    print(report)
    print(f"\n\n[written to {out_path} and {out_path.replace('.md', '.audit.json')}]", file=sys.stderr)


if __name__ == "__main__":
    main()
