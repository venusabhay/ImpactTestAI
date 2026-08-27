"""
Unit tests for the deterministic parts of analyze_change.py -- the parts
that don't need a live target repository, git history, or network access.

These are what the pilot CI workflow runs on every push/PR to prove the
analyzer itself isn't broken, independent of any target repository's
behavior. Fixture-/network-dependent behavior (git diffs, GitHub Actions
history, real npm test execution) is exercised separately by the fixture
smoke test in the CI workflow, not here.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import analyze_change as ac  # noqa: E402


# ---------------------------------------------------------------------------
# bucket_from_score
# ---------------------------------------------------------------------------

def test_bucket_from_score_boundaries():
    assert ac.bucket_from_score(0, thresholds=(1, 2, 4)) == "LOW"
    assert ac.bucket_from_score(1, thresholds=(1, 2, 4)) == "MEDIUM"
    assert ac.bucket_from_score(2, thresholds=(1, 2, 4)) == "HIGH"
    assert ac.bucket_from_score(4, thresholds=(1, 2, 4)) == "CRITICAL"
    assert ac.bucket_from_score(100, thresholds=(1, 2, 4)) == "CRITICAL"


# ---------------------------------------------------------------------------
# changed_line_ranges -- parses unified diff hunk headers
# ---------------------------------------------------------------------------

def test_changed_line_ranges_parses_hunk_header():
    diff_text = (
        "diff --git a/foo.js b/foo.js\n"
        "--- a/foo.js\n"
        "+++ b/foo.js\n"
        "@@ -10,0 +11,3 @@\n"
        "+line one\n"
        "+line two\n"
        "+line three\n"
    )
    ranges = ac.changed_line_ranges(diff_text, "foo.js")
    assert ranges == [(11, 14)]


def test_changed_line_ranges_ignores_other_files():
    diff_text = (
        "diff --git a/foo.js b/foo.js\n"
        "--- a/foo.js\n"
        "+++ b/foo.js\n"
        "@@ -1,0 +1,1 @@\n"
        "+x\n"
    )
    assert ac.changed_line_ranges(diff_text, "bar.js") == []


# ---------------------------------------------------------------------------
# find_route_handlers -- brace-matched Express route parsing
# ---------------------------------------------------------------------------

def test_find_route_handlers_finds_post_route_and_end_line():
    src = (
        'app.post("/verify", async (req, res) => {\n'
        "  doStuff();\n"
        "  if (x) {\n"
        "    doMore();\n"
        "  }\n"
        "});\n"
        "\n"
        'app.get("/health", (req, res) => {\n'
        "  res.send('ok');\n"
        "});\n"
    )
    handlers = ac.find_route_handlers(src)
    by_path = {h["path"]: h for h in handlers}
    assert set(by_path) == {"/verify", "/health"}
    assert by_path["/verify"]["method"] == "POST"
    assert by_path["/verify"]["start_line"] == 1
    assert by_path["/verify"]["end_line"] == 6
    assert by_path["/health"]["method"] == "GET"


# ---------------------------------------------------------------------------
# service_name_from_path
# ---------------------------------------------------------------------------

def test_service_name_from_path_matches_services_layout():
    assert ac.service_name_from_path("services/auth-service/server.js") == "auth-service"
    assert ac.service_name_from_path("frontend/src/App.jsx") is None
    assert ac.service_name_from_path("services/") is None


# ---------------------------------------------------------------------------
# scan_risk_patterns -- only matches added lines, dedupes by reason elsewhere
# ---------------------------------------------------------------------------

def test_scan_risk_patterns_only_matches_added_lines():
    diff_text = (
        "+++ b/foo.js\n"
        "+const cache = new Map();\n"
        "-const old = new Map();\n"
        " const unrelated = 1;\n"
    )
    hits = ac.scan_risk_patterns(diff_text)
    reasons = {h["reason"] for h in hits}
    assert "introduces or touches caching (statefulness / staleness risk)" in reasons
    assert "introduces new in-memory state" in reasons
    # The removed line (old cache) must not itself produce a hit.
    assert all(not h["line"].startswith("-") for h in hits)


def test_scan_risk_patterns_no_false_positive_on_unrelated_diff():
    diff_text = "+++ b/foo.js\n+const x = 1 + 1;\n"
    assert ac.scan_risk_patterns(diff_text) == []


# ---------------------------------------------------------------------------
# test_file_is_real_cross_service -- content-based detection, no filename magic
# ---------------------------------------------------------------------------

def test_real_cross_service_detection(tmp_path):
    real = tmp_path / "real.test.js"
    real.write_text("import axios from 'axios';\nimport { spawn } from 'child_process';\n"
                     "spawn('node', ['server.js']);\naxios.post('http://x/verify');\n")
    fake = tmp_path / "fake.test.js"
    fake.write_text("import request from 'supertest';\nrequest(app).post('/verify');\n")

    assert ac.test_file_is_real_cross_service(str(tmp_path), "real.test.js") is True
    assert ac.test_file_is_real_cross_service(str(tmp_path), "fake.test.js") is False
    assert ac.test_file_is_real_cross_service(str(tmp_path), "does-not-exist.test.js") is False


def test_module_import_detection(tmp_path):
    imports_it = tmp_path / "imports.test.js"
    imports_it.write_text("import app from './server.js';\n")
    duplicates_it = tmp_path / "duplicates.test.js"
    duplicates_it.write_text("const testApp = express();\n")

    assert ac.test_file_imports_module(str(tmp_path), "imports.test.js", "server.js") is True
    assert ac.test_file_imports_module(str(tmp_path), "duplicates.test.js", "server.js") is False


# ---------------------------------------------------------------------------
# final_recommendation -- the decision policy's branches
# ---------------------------------------------------------------------------

def _risk(risk_level="LOW", overall_confidence="HIGH", direct_test_coverage=True):
    return {
        "risk_level": risk_level,
        "confidence": {"overall": overall_confidence},
        "direct_test_coverage": direct_test_coverage,
    }


def test_recommendation_escalates_on_failure():
    outcomes = [{"result": "FAILED"}]
    decision, _ = ac.final_recommendation(_risk(), outcomes, {"selected_validations": [1]})
    assert decision == "ESCALATE"


def test_recommendation_escalates_on_inconclusive():
    outcomes = [{"result": "INCONCLUSIVE"}]
    decision, _ = ac.final_recommendation(_risk(), outcomes, {"selected_validations": [1]})
    assert decision == "ESCALATE"


def test_recommendation_escalates_when_nothing_ran():
    decision, _ = ac.final_recommendation(_risk(), [], {"selected_validations": []})
    assert decision == "ESCALATE"


def test_recommendation_requires_more_validation_on_high_risk_weak_coverage():
    risk = _risk(risk_level="HIGH", direct_test_coverage=False)
    outcomes = [{"result": "PASSED"}]
    decision, _ = ac.final_recommendation(risk, outcomes, {"selected_validations": [1]})
    assert decision == "REQUIRE_ADDITIONAL_VALIDATION"


def test_recommendation_requires_more_validation_on_low_confidence_even_if_low_risk():
    risk = _risk(risk_level="LOW", overall_confidence="LOW")
    outcomes = [{"result": "PASSED"}]
    decision, _ = ac.final_recommendation(risk, outcomes, {"selected_validations": [1]})
    assert decision == "REQUIRE_ADDITIONAL_VALIDATION"


def test_recommendation_accepts_when_passed_high_confidence_direct_coverage():
    risk = _risk(risk_level="HIGH", overall_confidence="HIGH", direct_test_coverage=True)
    outcomes = [{"result": "PASSED"}]
    decision, _ = ac.final_recommendation(risk, outcomes, {"selected_validations": [1]})
    assert decision == "ACCEPT"


# ---------------------------------------------------------------------------
# Probability is never a fabricated bucket (the Stage 1 correction) --
# a regression test for exactly the mistake that was caught and fixed.
# ---------------------------------------------------------------------------

def test_probability_is_always_unknown_never_a_bucket():
    change = {"diff_text": "+++ b/foo.js\n+const cache = new Map();\n"}
    impact = {"affected_entities": [], "uncertainty_sources": []}
    risk = ac.build_risk_assessment(change, impact)
    assert risk["probability"] == "UNKNOWN"
    assert "risk_indicators" in risk
    assert risk["probability"] not in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
