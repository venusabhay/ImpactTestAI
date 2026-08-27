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

This script only ever reads the target repository and runs its own
existing `npm test`. It does not modify, commit, or push anything there.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

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
POLICY_VERSION = "repo-evidence-rules-v2"

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

def find_route_handlers(file_text):
    """Locate Express route handlers: (method, path, start_line, end_line)."""
    lines = file_text.splitlines()
    handlers = []
    pattern = re.compile(r"app\.(get|post|put|delete|patch)\(\s*[\"'`]([^\"'`]+)[\"'`]")
    for i, line in enumerate(lines):
        m = pattern.search(line)
        if not m:
            continue
        method, path = m.group(1), m.group(2)
        # Find the matching close of app.METHOD( ... ) by paren balance
        start_idx = m.start()
        depth = 0
        end_line = i
        started = False
        for j in range(i, len(lines)):
            scan_from = start_idx if j == i else 0
            for ch in lines[j][scan_from:]:
                if ch == "(":
                    depth += 1
                    started = True
                elif ch == ")":
                    depth -= 1
            if started and depth <= 0:
                end_line = j
                break
        handlers.append({
            "method": method.upper(),
            "path": path,
            "start_line": i + 1,
            "end_line": end_line + 1,
        })
    return handlers


def service_name_from_path(repo_relative_path):
    m = re.match(r"services/([^/]+)/", repo_relative_path)
    return m.group(1) if m else None


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


def find_callers(repo, route_path, own_file):
    hits = grep_repo(repo, route_path, exclude_paths={own_file})
    callers = []
    for h in hits:
        looks_like_call = bool(re.search(r"axios|fetch\(", h["snippet"]))
        callers.append({**h, "looks_like_http_call": looks_like_call,
                         "calling_service": service_name_from_path(h["file"])})
    return callers


def find_test_evidence(repo, route_path):
    hits = grep_repo(repo, route_path)
    return [h for h in hits if h["file"].endswith(".test.js")]


def test_file_imports_module(repo, test_file, module_basename):
    """Does the test file actually import the module it claims to test,
    or does it hand-duplicate its own app (a real, generically-detectable
    gap seen in this repository)?"""
    path = os.path.join(repo, test_file)
    if not os.path.exists(path):
        return None
    with open(path, "r", errors="ignore") as f:
        text = f.read()
    return bool(re.search(rf"""(from|require)\(?['"]\.?/?{re.escape(module_basename)}['"]""", text)) \
        or bool(re.search(rf"""(from|require)\(?['"]\./{re.escape(module_basename.replace('.js',''))}['"]""", text))


def build_impact_assessment(repo, change):
    affected_entities = []
    uncertainty_sources = []

    for path in change["changed_files"]:
        full_path = os.path.join(repo, path)
        if not os.path.exists(full_path) or not path.endswith(".js"):
            continue
        with open(full_path, "r", errors="ignore") as f:
            file_text = f.read()

        service = service_name_from_path(path)
        touched_ranges = changed_line_ranges(change["diff_text_u0"], path)
        handlers = find_route_handlers(file_text)

        for h in handlers:
            overlaps = any(not (h["end_line"] < s or h["start_line"] > e) for s, e in touched_ranges)
            if not overlaps:
                continue

            evidence = [{
                "type": "SOURCE_CODE",
                "description": f"{path}:{h['start_line']}-{h['end_line']} defines {h['method']} {h['path']}, "
                                f"and the diff modifies lines within that handler.",
            }]

            # Direct entity: the endpoint itself
            direct_confidence = "HIGH"  # directly observed in the diff + file
            affected_entities.append({
                "entity": f"{service or path}: {h['method']} {h['path']}",
                "impact_type": "DIRECT",
                "confidence": direct_confidence,
                "evidence": evidence,
            })

            # Transitive: other services calling this route path
            callers = find_callers(repo, h["path"], own_file=path)
            caller_services = sorted({c["calling_service"] for c in callers if c["calling_service"] and c["calling_service"] != service})
            for cs in caller_services:
                cs_hits = [c for c in callers if c["calling_service"] == cs]
                affected_entities.append({
                    "entity": f"{cs} (via calls to {h['path']})",
                    "impact_type": "TRANSITIVE",
                    "confidence": "HIGH" if any(c["looks_like_http_call"] for c in cs_hits) else "MEDIUM",
                    "evidence": [{
                        "type": "STATIC_ANALYSIS",
                        "description": f"{c['file']}:{c['line']} references \"{h['path']}\" "
                                        f"{'in what looks like an HTTP call' if c['looks_like_http_call'] else '(reference found, call pattern not confirmed)'}.",
                    } for c in cs_hits],
                })

            # Test coverage evidence
            test_hits = find_test_evidence(repo, h["path"])
            same_service_tests = [t for t in test_hits if service_name_from_path(t["file"]) == service]
            if same_service_tests:
                test_file = same_service_tests[0]["file"]
                imports_module = test_file_imports_module(repo, test_file, os.path.basename(path))
                affected_entities.append({
                    "entity": f"Existing test coverage: {test_file}",
                    "impact_type": "TEST_COVERAGE",
                    "confidence": "MEDIUM" if imports_module else "LOW",
                    "evidence": [{
                        "type": "TEST_EXECUTION",
                        "description": f"{t['file']}:{t['line']} references \"{h['path']}\".",
                    } for t in same_service_tests] + [{
                        "type": "STATIC_ANALYSIS",
                        "description": (
                            f"{test_file} DOES import/require the changed module directly."
                            if imports_module else
                            f"{test_file} does NOT import or require {os.path.basename(path)} -- "
                            f"it appears to re-implement its own test version of the route(s) instead. "
                            f"A passing result here does not confirm the actual changed code path was exercised."
                        ),
                    }],
                })
            else:
                uncertainty_sources.append(
                    f"No test file evidence found for {h['method']} {h['path']} in service '{service}'."
                )

            # Explicit unknowns -- things this analysis structurally cannot know
            uncertainty_sources.append(
                f"Production call volume / exposure for {h['method']} {h['path']}: Unknown / insufficient evidence "
                f"(no production telemetry access in this slice)."
            )
            uncertainty_sources.append(
                f"Historical incident rate for this endpoint: Unknown / insufficient evidence "
                f"(no incident-system access in this slice)."
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
    structural_exposure_score = len(caller_services)

    changed_paths = [e["entity"].split(": ", 1)[-1] for e in impact["affected_entities"] if e["impact_type"] == "DIRECT"]
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
    direct_test_coverage = any(e["confidence"] == "MEDIUM" for e in test_coverage_entities)  # MEDIUM = imports module

    impact_confidence = "HIGH" if structural_exposure_score > 0 or changed_paths else "LOW"
    # Always LOW: there is no basis to be more confident than that about a
    # dimension (probability) this policy version explicitly declines to estimate.
    probability_confidence = "LOW"
    evidence_confidence = "MEDIUM" if direct_test_coverage else "LOW"

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
            "score": structural_exposure_score,
        },
        "sensitive_name_hit": sensitive_name_hit,
        "risk_pattern_hits": pattern_hits,
        "direct_test_coverage": direct_test_coverage,
        "policy_version": POLICY_VERSION,
    }


# ---------------------------------------------------------------------------
# 4. Validation Decision + real execution
# ---------------------------------------------------------------------------

def build_validation_decision(repo, change, risk):
    services = sorted({service_name_from_path(p) for p in change["changed_files"] if service_name_from_path(p)})
    selected, rejected = [], []

    for svc in services:
        svc_dir = os.path.join(repo, "services", svc)
        pkg_path = os.path.join(svc_dir, "package.json")
        has_test_script = False
        if os.path.exists(pkg_path):
            with open(pkg_path) as f:
                pkg = json.load(f)
            has_test_script = "test" in pkg.get("scripts", {})
        if has_test_script:
            reason = (
                f"'{svc}' service's existing test suite is the best available real validation for this change "
                f"(exists, runs via 'npm test')."
            )
            if not risk["direct_test_coverage"]:
                reason += (" NOTE: repo-evidence indicates this suite does not import the changed module directly "
                            "(it re-implements its own routes for testing) -- treat a PASS here as a weak signal, "
                            "not confirmation that the changed code path was exercised.")
            selected.append({
                "type": "INTEGRATION_TEST",
                "target": svc,
                "command": "npm test",
                "decision_reason": reason,
            })
        else:
            rejected.append({
                "type": "INTEGRATION_TEST",
                "target": svc,
                "decision_reason": f"No 'test' script found in {svc}/package.json.",
            })

    # Explicitly reject the one validation that would matter most, and say why
    if risk["structural_exposure"]["caller_services"]:
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


def run_validation(repo, node_bin_dir, selected):
    outcomes = []
    env = os.environ.copy()
    env["PATH"] = f"{node_bin_dir}:{env.get('PATH', '')}"
    for v in selected:
        svc_dir = os.path.join(repo, "services", v["target"])
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

def render_report(change, impact, risk, validation_decision, outcomes, recommendation, repo, node_bin_dir):
    decision, decision_reason = recommendation
    direct = [e for e in impact["affected_entities"] if e["impact_type"] == "DIRECT"]
    transitive = [e for e in impact["affected_entities"] if e["impact_type"] == "TRANSITIVE"]
    test_cov = [e for e in impact["affected_entities"] if e["impact_type"] == "TEST_COVERAGE"]

    lines = []
    lines.append("# Change Risk & Validation Report\n")
    lines.append(f"*Generated {datetime.now(timezone.utc).isoformat()}Z from repository at `{repo}`, "
                  f"comparing working tree against `{change['base_ref']}` (HEAD `{change['repo_head'][:10]}`).*\n")

    lines.append("## CHANGE\n")
    direct_desc = "; ".join(e["entity"] for e in direct) or "no route-level change detected"
    lines.append(f"{direct_desc}.\n")
    lines.append(f"```\n{change['diff_stat']}\n```\n")

    lines.append("## POTENTIAL IMPACT\n")
    for e in direct:
        lines.append(f"- **{e['entity']}** (direct) -- confidence: {e['confidence']}")
    for e in transitive:
        lines.append(f"- **{e['entity']}** (transitive) -- confidence: {e['confidence']}")
    lines.append("")

    lines.append("## EVIDENCE\n")
    for e in direct + transitive + test_cov:
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

    lines.append("## WHY\n")
    why = []
    if risk["structural_exposure"]["score"]:
        why.append(f"The changed endpoint is called by {risk['structural_exposure']['score']} other service(s): "
                    f"{', '.join(risk['structural_exposure']['caller_services'])}.")
    if risk["sensitive_name_hit"]:
        why.append("The changed route's name/path matches a security-sensitive pattern (auth/token/password/etc.).")
    if risk["risk_indicators"]:
        why.append("The diff contains factors associated with elevated risk: " + "; ".join(risk["risk_indicators"]) +
                    ". These are indicators the risk level accounts for, not a measured probability of failure.")
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

    lines.append(f"---\n*Risk/validation rules: `{risk['policy_version']}`. "
                  f"Re-running this analysis with the same policy version against the same repo state and "
                  f"ref should reproduce this exact assessment.*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Vertical-slice change-risk analyzer (design8/9 slice).")
    parser.add_argument("repo", help="Path to the target repository")
    parser.add_argument("--against", default="HEAD", help="Git ref to diff the working tree against")
    parser.add_argument("--node-bin", default=os.environ.get("NODE_BIN_DIR", ""),
                         help="Directory containing a working node/npm binary")
    parser.add_argument("--no-run", action="store_true", help="Skip actually executing validation")
    parser.add_argument("--out", default=None, help="Output report path (markdown)")
    args = parser.parse_args()

    repo = os.path.abspath(args.repo)
    change = get_change(repo, args.against)
    if not change["changed_files"]:
        print("No changes found against", args.against, file=sys.stderr)
        sys.exit(1)

    impact = build_impact_assessment(repo, change)
    risk = build_risk_assessment(change, impact)
    validation_decision = build_validation_decision(repo, change, risk)

    outcomes = []
    if not args.no_run and validation_decision["selected_validations"]:
        if not args.node_bin:
            print("WARNING: --node-bin not provided; skipping execution.", file=sys.stderr)
        else:
            outcomes = run_validation(repo, args.node_bin, validation_decision["selected_validations"])

    recommendation = final_recommendation(risk, outcomes, validation_decision)

    report = render_report(change, impact, risk, validation_decision, outcomes, recommendation, repo, args.node_bin)

    audit_record = {
        "repo": repo, "base_ref": args.against, "repo_head": change["repo_head"],
        "policy_version": POLICY_VERSION,
        "changed_files": change["changed_files"],
        "impact": impact, "risk": risk, "validation_decision": validation_decision,
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
