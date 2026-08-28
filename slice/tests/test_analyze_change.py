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
import subprocess
import sys
from unittest.mock import patch

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

# Route detection and component/service identification moved to
# discovery.py as part of ADAPT_ARCHITECTURE_DISCOVERY (generalized route
# detection, package.json-based component discovery) -- see
# tests/test_discovery.py for their coverage, and
# tests/test_known_repos_regression.py for end-to-end coverage against the
# real social-media-mini and user-management-app repository structures.


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


# ---------------------------------------------------------------------------
# Generic-path guard (ADAPT_ARCHITECTURE_DISCOVERY) -- a route path with no
# meaningful segment (bare "/") is a substring of nearly everything; caller/
# test-evidence search against it must be skipped rather than flood the
# report with false positives. General guard, not tied to any repository.
# ---------------------------------------------------------------------------

def test_find_callers_skips_bare_root_path(tmp_path):
    (tmp_path / "unrelated.js").write_text("const x = '/some/unrelated/path';\n")
    assert ac.find_callers(str(tmp_path), "/", own_file="server.js", components=[]) == []


def test_find_test_evidence_skips_bare_root_path(tmp_path):
    (tmp_path / "whatever.test.js").write_text("const x = '/anything';\n")
    assert ac.find_test_evidence(str(tmp_path), "/") == []


# ---------------------------------------------------------------------------
# run_validation -- configurable timeout (VALIDATION_TIMEOUT_PROPOSAL.md,
# Option A: implemented). Written after a real diagnostic against
# tt-a1i/archify: a healthy, 0-failure, 723-test suite took 338s and was
# reported ESCALATE purely because it exceeded the then-hardcoded 180s
# limit. The limit is now a parameter (validation_timeout_seconds, default
# 180 -- unchanged) instead of a literal, and the timeout actually used is
# recorded on every outcome. subprocess.run is mocked to raise
# TimeoutExpired in most of these so timeout handling is exercised
# deterministically, without waiting 180+ real seconds; one test below
# (test_explicit_timeout_extension_can_turn_a_timeout_into_a_real_pass)
# uses a real subprocess deliberately, to prove the threading works
# end-to-end, not just against a mock.
# ---------------------------------------------------------------------------

def _selected_validation(command="npm test"):
    return [{"type": "INTEGRATION_TEST", "target": "component", "target_dir": "component", "command": command}]


def test_run_validation_reports_inconclusive_on_timeout(tmp_path):
    (tmp_path / "component").mkdir()
    with patch("analyze_change.subprocess.run",
               side_effect=subprocess.TimeoutExpired(cmd="npm test", timeout=180)):
        outcomes = ac.run_validation(str(tmp_path), "", _selected_validation(), npm_install=False)
    assert len(outcomes) == 1
    outcome = outcomes[0]
    # The core contract: a timeout is never laundered into a verdict.
    assert outcome["result"] == "INCONCLUSIVE"
    assert outcome["result"] not in ("PASSED", "FAILED")
    assert outcome["exit_code"] is None
    assert outcome["classification"] == "INFRASTRUCTURE (timeout)"


def test_run_validation_default_timeout_is_180_seconds(tmp_path):
    """The default must remain 180s, per the approved proposal -- this is
    not a change to behavior, only to how the value reaches subprocess.run
    (parameter instead of a literal)."""
    (tmp_path / "component").mkdir()
    with patch("analyze_change.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="npm test", timeout=180)
        ac.run_validation(str(tmp_path), "", _selected_validation(), npm_install=False)
    _, kwargs = mock_run.call_args
    assert kwargs["timeout"] == 180


def test_run_validation_passes_through_an_explicit_timeout(tmp_path):
    """An operator-supplied timeout reaches subprocess.run exactly --
    the whole point of Option A."""
    (tmp_path / "component").mkdir()
    with patch("analyze_change.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="npm test", timeout=600)
        ac.run_validation(str(tmp_path), "", _selected_validation(), npm_install=False,
                           validation_timeout_seconds=600)
    _, kwargs = mock_run.call_args
    assert kwargs["timeout"] == 600


def test_timeout_seconds_recorded_on_both_timeout_and_completed_outcomes(tmp_path):
    """Every validation outcome -- whether it timed out or actually
    completed -- records the timeout that was in effect, so a report/audit
    record is self-describing without reading source code."""
    (tmp_path / "component").mkdir()

    with patch("analyze_change.subprocess.run",
               side_effect=subprocess.TimeoutExpired(cmd="npm test", timeout=45)):
        timed_out = ac.run_validation(str(tmp_path), "", _selected_validation(), npm_install=False,
                                       validation_timeout_seconds=45)
    assert timed_out[0]["timeout_seconds"] == 45

    completed_result = subprocess.CompletedProcess(args="npm test", returncode=0, stdout="ok\n", stderr="")
    with patch("analyze_change.subprocess.run", return_value=completed_result):
        completed = ac.run_validation(str(tmp_path), "", _selected_validation(), npm_install=False,
                                       validation_timeout_seconds=45)
    assert completed[0]["result"] == "PASSED"
    assert completed[0]["timeout_seconds"] == 45


def test_timeout_outcome_never_reaches_accept_or_require_additional_validation():
    """End-to-end contract check: an INCONCLUSIVE/timeout outcome must
    produce ESCALATE from final_recommendation() regardless of risk level
    or confidence -- a timeout is not evidence about the change itself,
    so nothing about the rest of the assessment may override it."""
    timeout_outcome = [{
        "target": "component", "command": "npm test", "result": "INCONCLUSIVE",
        "exit_code": None, "stdout_tail": "", "stderr_tail": "timed out",
        "classification": "INFRASTRUCTURE (timeout)", "timeout_seconds": 180,
    }]
    for risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        for overall_confidence in ("LOW", "MEDIUM", "HIGH"):
            risk = _risk(risk_level=risk_level, overall_confidence=overall_confidence, direct_test_coverage=True)
            decision, _ = ac.final_recommendation(risk, timeout_outcome, {"selected_validations": [1]})
            assert decision == "ESCALATE"


# ---------------------------------------------------------------------------
# Integration-level test: a REAL subprocess (not mocked) that a short
# default timeout cannot finish within, but an explicitly extended timeout
# can -- proving the parameter threading works end-to-end, not just
# against a mock, and directly demonstrating the Archify scenario
# (a healthy command that is merely slow) at a scale a test suite can run
# in about a second instead of several minutes.
# ---------------------------------------------------------------------------

def test_explicit_timeout_extension_can_turn_a_timeout_into_a_real_pass(tmp_path):
    (tmp_path / "component").mkdir()
    selected = _selected_validation(command="sleep 1 && exit 0")

    too_short = ac.run_validation(str(tmp_path), "", selected, npm_install=False,
                                   validation_timeout_seconds=0.2)
    assert too_short[0]["result"] == "INCONCLUSIVE"
    assert too_short[0]["classification"] == "INFRASTRUCTURE (timeout)"
    assert too_short[0]["timeout_seconds"] == 0.2

    long_enough = ac.run_validation(str(tmp_path), "", selected, npm_install=False,
                                     validation_timeout_seconds=5)
    assert long_enough[0]["result"] == "PASSED"
    assert long_enough[0]["exit_code"] == 0
    assert long_enough[0]["timeout_seconds"] == 5
