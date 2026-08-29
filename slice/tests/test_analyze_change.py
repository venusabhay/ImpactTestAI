"""
Unit tests for the deterministic parts of analyze_change.py -- the parts
that don't need a live target repository, git history, or network access.

These are what the pilot CI workflow runs on every push/PR to prove the
analyzer itself isn't broken, independent of any target repository's
behavior. Fixture-/network-dependent behavior (git diffs, GitHub Actions
history, real npm test execution) is exercised separately by the fixture
smoke test in the CI workflow, not here.
"""
import http.client
import json
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


# ---------------------------------------------------------------------------
# run_validation -- npm install failure handling (see
# docs/decisions/PIPELINE_FAIL_SAFE_DESIGN.md, written after two real pilot crashes:
# an unhandled subprocess.TimeoutExpired from "npm install" itself, and an
# unhandled http.client.IncompleteRead from CI-history fetching -- both
# previously took the whole process down with no report.md/audit.json
# produced at all. subprocess.run is mocked so the three install shapes
# (timeout, non-zero exit, success) are distinguished deterministically,
# without a real 300-second wait.
# ---------------------------------------------------------------------------

def _install_side_effect(install_result_or_exception):
    """Returns a subprocess.run side_effect that only affects the "npm
    install" call -- the validation command, if reached, gets a plain
    successful CompletedProcess. Raises if the validation command runs
    when it shouldn't (install failed/timed out) -- the "do not silently
    continue to validation" requirement, checked structurally."""
    def side_effect(cmd, **kwargs):
        if cmd == "npm install":
            if isinstance(install_result_or_exception, BaseException):
                raise install_result_or_exception
            return install_result_or_exception
        raise AssertionError(f"validation command {cmd!r} must not run when npm install did not succeed")
    return side_effect


def test_run_validation_npm_install_timeout_is_inconclusive_not_a_crash(tmp_path):
    (tmp_path / "component").mkdir()
    selected = _selected_validation()
    timeout_exc = subprocess.TimeoutExpired(cmd="npm install", timeout=ac.NPM_INSTALL_TIMEOUT_SECONDS)
    with patch("analyze_change.subprocess.run", side_effect=_install_side_effect(timeout_exc)):
        outcomes = ac.run_validation(str(tmp_path), "", selected, npm_install=True)
    assert len(outcomes) == 1
    o = outcomes[0]
    assert o["command"] == "npm install"
    assert o["result"] == "INCONCLUSIVE"
    assert o["result"] not in ("PASSED", "FAILED")
    assert o["exit_code"] is None
    assert o["classification"] == "INFRASTRUCTURE (dependency install timed out)"
    assert o["install_timeout_seconds"] == ac.NPM_INSTALL_TIMEOUT_SECONDS


def test_run_validation_npm_install_nonzero_exit_is_distinct_from_timeout(tmp_path):
    (tmp_path / "component").mkdir()
    selected = _selected_validation()
    failed_install = subprocess.CompletedProcess(args="npm install", returncode=1, stdout="", stderr="ENOENT")
    with patch("analyze_change.subprocess.run", side_effect=_install_side_effect(failed_install)):
        outcomes = ac.run_validation(str(tmp_path), "", selected, npm_install=True)
    assert len(outcomes) == 1
    o = outcomes[0]
    assert o["result"] == "INCONCLUSIVE"
    assert o["exit_code"] == 1
    # The whole point: a human/audit reader must be able to tell these two
    # INFRASTRUCTURE outcomes apart.
    assert o["classification"] == "INFRASTRUCTURE (dependency install failed)"
    assert o["classification"] != "INFRASTRUCTURE (dependency install timed out)"
    assert o["install_timeout_seconds"] == ac.NPM_INSTALL_TIMEOUT_SECONDS


def test_run_validation_npm_install_success_still_reaches_validation(tmp_path):
    """Confirms the "do not silently continue to validation" rule is a
    conditional check, not an accidental removal of the validation step
    entirely -- a successful install still runs the real command."""
    (tmp_path / "component").mkdir()
    selected = _selected_validation(command="echo ok")
    ok_install = subprocess.CompletedProcess(args="npm install", returncode=0, stdout="", stderr="")

    def side_effect(cmd, **kwargs):
        if cmd == "npm install":
            return ok_install
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok\n", stderr="")

    with patch("analyze_change.subprocess.run", side_effect=side_effect):
        outcomes = ac.run_validation(str(tmp_path), "", selected, npm_install=True)
    assert len(outcomes) == 1
    assert outcomes[0]["command"] == "echo ok"
    assert outcomes[0]["result"] == "PASSED"


def test_install_timeout_outcome_still_escalates():
    """End-to-end contract check, same shape as the existing
    validation-timeout test: an install-timeout INCONCLUSIVE outcome must
    still force ESCALATE regardless of risk level or confidence."""
    install_timeout_outcome = [{
        "target": "component", "command": "npm install", "result": "INCONCLUSIVE",
        "exit_code": None, "stdout_tail": "", "stderr_tail": "timed out",
        "classification": "INFRASTRUCTURE (dependency install timed out)",
        "install_timeout_seconds": ac.NPM_INSTALL_TIMEOUT_SECONDS,
    }]
    for risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        for overall_confidence in ("LOW", "MEDIUM", "HIGH"):
            risk = _risk(risk_level=risk_level, overall_confidence=overall_confidence, direct_test_coverage=True)
            decision, _ = ac.final_recommendation(risk, install_timeout_outcome, {"selected_validations": [1]})
            assert decision == "ESCALATE"


def _minimal_report_args(outcomes, ci_history=None):
    """The smallest valid set of render_report() arguments -- enough to
    exercise every line render_report() actually reaches for these test
    scenarios (no discovered impact, no CI history or a failed CI-history
    fetch), so "does this crash, and does the output look right" can be
    checked directly against the real function rather than inferred from
    its inputs alone."""
    change = {"base_ref": "HEAD", "repo_head": "0" * 40, "diff_stat": "1 file changed"}
    impact = {"affected_entities": [], "uncertainty_sources": []}
    risk = {
        "risk_level": "LOW", "business_impact": "LOW", "exposure": "LOW",
        "probability": "UNKNOWN", "probability_reason": "not estimated",
        "confidence": {"overall": "LOW", "impact_confidence": "LOW",
                       "probability_confidence": "LOW", "evidence_confidence": "LOW"},
        "risk_indicators": [], "sensitive_name_hit": False, "direct_test_coverage": False,
        "structural_exposure": {"caller_services": [], "middleware_route_count": 0},
        "policy_version": ac.POLICY_VERSION,
    }
    validation_decision = {"selected_validations": [], "rejected_validations": []}
    recommendation = ac.final_recommendation(risk, outcomes, validation_decision)
    return change, impact, risk, validation_decision, recommendation


def test_npm_install_timeout_produces_a_renderable_report_and_audit_record():
    """Confirms the failure path actually reaches report.md/audit.json,
    not just that the outcome dict looks right in isolation -- calls the
    real render_report() and a real json.dumps(), the same two steps
    main() performs, against the exact outcome shape the timeout handler
    produces."""
    outcomes = [{
        "target": "component", "command": "npm install", "result": "INCONCLUSIVE",
        "exit_code": None, "stdout_tail": "", "stderr_tail": "timed out",
        "classification": "INFRASTRUCTURE (dependency install timed out)",
        "install_timeout_seconds": ac.NPM_INSTALL_TIMEOUT_SECONDS,
    }]
    change, impact, risk, validation_decision, recommendation = _minimal_report_args(outcomes)
    report = ac.render_report(change, impact, risk, validation_decision, outcomes, recommendation,
                               "/tmp/repo", "", ci_history=None, run_id="test-run-id")
    assert "INCONCLUSIVE" in report
    assert "INFRASTRUCTURE (dependency install timed out)" in report
    assert f"install timeout allowed: {ac.NPM_INSTALL_TIMEOUT_SECONDS}s" in report
    assert "ESCALATE" in report
    # Never fabricated as a pass or a fail:
    assert "**PASSED**" not in report
    assert "**FAILED**" not in report
    # Must be a valid, complete audit record -- json.dumps must not raise.
    audit_record = {"outcomes": outcomes, "risk": risk, "recommendation": {"decision": recommendation[0]}}
    json.dumps(audit_record)


# ---------------------------------------------------------------------------
# fetch_ci_history -- transient network/HTTP failure handling (see
# docs/decisions/PIPELINE_FAIL_SAFE_DESIGN.md). _gh_api_get is mocked so
# IncompleteRead and connection failures are exercised deterministically,
# without a real network dependency.
# ---------------------------------------------------------------------------

def test_fetch_ci_history_handles_incomplete_read_without_crashing():
    with patch("analyze_change._gh_api_get", side_effect=http.client.IncompleteRead(b"partial")):
        record = ac.fetch_ci_history("owner/repo", "myservice")
    assert record["available"] is False
    assert "IncompleteRead" in record["error"]
    assert record["historical_signal"] == "UNKNOWN / insufficient evidence"
    # Never fabricated: no counts, no job results, despite the crash.
    assert record["service_failures"] == 0
    assert record["service_successes"] == 0
    assert record["service_job_results"] == []


def test_fetch_ci_history_handles_connection_error_without_crashing():
    with patch("analyze_change._gh_api_get", side_effect=ConnectionResetError("connection reset by peer")):
        record = ac.fetch_ci_history("owner/repo", "myservice")
    assert record["available"] is False
    assert "ConnectionResetError" in record["error"]
    assert record["service_job_results"] == []


def test_fetch_ci_history_distinguishes_unreachable_from_no_matching_history():
    """The two 'nothing to report' shapes must stay distinguishable: a
    crash-caused UNKNOWN must not read the same as a clean fetch that
    simply found no matching CI job."""
    with patch("analyze_change._gh_api_get", side_effect=http.client.IncompleteRead(b"partial")):
        unreachable = ac.fetch_ci_history("owner/repo", "myservice")
    with patch("analyze_change._gh_api_get", return_value={"workflow_runs": []}):
        no_history = ac.fetch_ci_history("owner/repo", "myservice")

    assert unreachable["available"] is False
    assert no_history["available"] is True
    assert unreachable["error"] is not None
    assert no_history["error"] is None
    assert unreachable["historical_signal"] != no_history["historical_signal"]


def test_fetch_ci_history_preserves_partial_evidence_when_a_later_fetch_fails():
    """Two runs' worth of job data is fetched; the second fetch fails.
    Evidence already collected from the first run must survive, not be
    discarded because a later step crashed."""
    runs_response = {
        "workflow_runs": [
            {"id": 1, "path": ".github/workflows/ci.yml", "status": "completed",
             "created_at": "2026-01-01T00:00:00Z", "url": "https://api.github.com/run/1",
             "html_url": "https://x/1"},
            {"id": 2, "path": ".github/workflows/ci.yml", "status": "completed",
             "created_at": "2026-01-02T00:00:00Z", "url": "https://api.github.com/run/2",
             "html_url": "https://x/2"},
        ]
    }
    jobs_ok = {"jobs": [{"name": "Test (myservice)", "conclusion": "success"}]}

    def side_effect(url, timeout=15):
        if "actions/runs?per_page=" in url:
            return runs_response
        if url == "https://api.github.com/run/1/jobs":
            return jobs_ok
        if url == "https://api.github.com/run/2/jobs":
            raise http.client.IncompleteRead(b"partial")
        raise AssertionError(f"unexpected url {url}")

    with patch("analyze_change._gh_api_get", side_effect=side_effect):
        record = ac.fetch_ci_history("owner/repo", "myservice")

    assert record["available"] is True
    assert len(record["service_job_results"]) == 1  # from run 1, preserved
    assert record["service_successes"] == 1
    assert any("Could not fetch job detail for run 2" in lim for lim in record["limitations"])
    # The successfully-collected evidence is real, not invented for the
    # run whose fetch failed:
    assert record["service_job_results"][0]["run_id"] == 1


def test_ci_history_crash_produces_a_renderable_report_and_never_fabricates():
    """Same 'does this actually reach report.md/audit.json' check as the
    npm-install test above, for the CI-history crash path."""
    with patch("analyze_change._gh_api_get", side_effect=http.client.IncompleteRead(b"partial")):
        ci_history = {"myservice": ac.fetch_ci_history("owner/repo", "myservice")}
    outcomes = []
    change, impact, risk, validation_decision, recommendation = _minimal_report_args(outcomes, ci_history)
    report = ac.render_report(change, impact, risk, validation_decision, outcomes, recommendation,
                               "/tmp/repo", "", ci_history=ci_history, run_id="test-run-id")
    assert "UNKNOWN / insufficient evidence" in report
    assert "IncompleteRead" in report
    # Never fabricated as a clean or a failing history:
    assert "0 failed" not in report  # would imply a real, examined-and-clean history
    assert "confirmed CI job failure" not in report
    audit_record = {"ci_history": ci_history, "risk": risk, "recommendation": {"decision": recommendation[0]}}
    json.dumps(audit_record)


# ---------------------------------------------------------------------------
# fetch_ci_history -- generic workflow-path discovery (see
# slice/CI_WORKFLOW_DISCOVERY_INVESTIGATION.md). Prior behavior matched
# only the single exact path ".github/workflows/ci.yml"; measured against
# 10 real repositories to hide real, retrievable CI history on any repo
# using a different filename. Now matches any path starting with
# ".github/workflows/" (real, repository-authored workflow files), still
# excluding GitHub-managed "dynamic/..." runs (Dependabot, CodeQL,
# Copilot, Pages) surfaced through the same API. No filename allowlist;
# no per-repository special case.
# ---------------------------------------------------------------------------

def _runs_data(entries):
    """entries: list of (run_id, path) tuples, all reported as completed."""
    return {
        "workflow_runs": [
            {
                "id": run_id, "path": path, "status": "completed",
                "created_at": "2026-01-01T00:00:00Z",
                "url": f"https://api.github.com/run/{run_id}",
                "html_url": f"https://x/{run_id}",
            }
            for run_id, path in entries
        ]
    }


def _jobs_response(job_name, conclusion="success"):
    return {"jobs": [{"name": job_name, "conclusion": conclusion}]}


def test_fetch_ci_history_still_accepts_the_original_ci_yml_path():
    runs = _runs_data([(1, ".github/workflows/ci.yml")])

    def side_effect(url, timeout=15):
        if "actions/runs?per_page=" in url:
            return runs
        if url == "https://api.github.com/run/1/jobs":
            return _jobs_response("Test (myservice)")
        raise AssertionError(f"unexpected url {url}")

    with patch("analyze_change._gh_api_get", side_effect=side_effect):
        record = ac.fetch_ci_history("owner/repo", "myservice")
    assert record["runs_examined"] == 1
    assert record["service_successes"] == 1


def test_fetch_ci_history_accepts_a_differently_named_workflow_file():
    """The originally-reported gap: a repo whose real CI workflow is
    named something other than ci.yml (here, node.js.yml -- matching the
    real saisilinus/node-express-mongoose-typescript-boilerplate case
    from the prior pilot round) must no longer be invisible."""
    runs = _runs_data([(1, ".github/workflows/node.js.yml")])

    def side_effect(url, timeout=15):
        if "actions/runs?per_page=" in url:
            return runs
        if url == "https://api.github.com/run/1/jobs":
            return _jobs_response("Test (myservice)")
        raise AssertionError(f"unexpected url {url}")

    with patch("analyze_change._gh_api_get", side_effect=side_effect):
        record = ac.fetch_ci_history("owner/repo", "myservice")
    assert record["runs_examined"] == 1
    assert record["service_successes"] == 1


def test_fetch_ci_history_accepts_an_arbitrary_other_workflow_filename():
    """No filename allowlist: an unrelated, never-seen-before real
    workflow filename is accepted purely because of where it lives."""
    runs = _runs_data([(1, ".github/workflows/build-and-verify.yml")])

    def side_effect(url, timeout=15):
        if "actions/runs?per_page=" in url:
            return runs
        if url == "https://api.github.com/run/1/jobs":
            return _jobs_response("Test (myservice)")
        raise AssertionError(f"unexpected url {url}")

    with patch("analyze_change._gh_api_get", side_effect=side_effect):
        record = ac.fetch_ci_history("owner/repo", "myservice")
    assert record["runs_examined"] == 1
    assert record["service_successes"] == 1


def test_fetch_ci_history_excludes_github_managed_dynamic_paths():
    """dynamic/... runs (Dependabot, CodeQL, Copilot, Pages) are not
    repository-authored workflows and must not be treated as CI history,
    even though they come back from the same API call. If the analyzer
    incorrectly fetched job detail for the dynamic run, the side_effect
    below would raise."""
    runs = _runs_data([
        (1, "dynamic/dependabot/dependabot-updates"),
        (2, ".github/workflows/ci.yml"),
    ])

    def side_effect(url, timeout=15):
        if "actions/runs?per_page=" in url:
            return runs
        if url == "https://api.github.com/run/2/jobs":
            return _jobs_response("Test (myservice)")
        raise AssertionError(f"should not fetch job detail for a dynamic/ path: {url}")

    with patch("analyze_change._gh_api_get", side_effect=side_effect):
        record = ac.fetch_ci_history("owner/repo", "myservice")
    assert record["runs_examined"] == 1  # only the real workflow run, not the dynamic one
    assert record["service_successes"] == 1


def test_fetch_ci_history_job_matching_unchanged_under_a_non_ci_yml_path():
    """The existing job-name-vs-service discrimination (prefer a job
    whose name signals an actual test run over one that merely mentions
    the service, e.g. a Docker build) must behave identically regardless
    of which real workflow filename the jobs came from."""
    runs = _runs_data([(1, ".github/workflows/node.js.yml")])
    jobs = {"jobs": [
        {"name": "Docker Build Test (myservice)", "conclusion": "success"},
        {"name": "Test (myservice)", "conclusion": "failure"},
    ]}

    def side_effect(url, timeout=15):
        if "actions/runs?per_page=" in url:
            return runs
        if url == "https://api.github.com/run/1/jobs":
            return jobs
        raise AssertionError(f"unexpected url {url}")

    with patch("analyze_change._gh_api_get", side_effect=side_effect):
        record = ac.fetch_ci_history("owner/repo", "myservice")
    # The Docker job is excluded even though it mentions the service by name;
    # only the real test-named job is counted.
    assert len(record["service_job_results"]) == 1
    assert record["service_job_results"][0]["job_name"] == "Test (myservice)"
    assert record["service_failures"] == 1
    assert record["service_successes"] == 0


def test_fetch_ci_history_zero_usable_runs_is_still_honest_insufficient_evidence():
    """A repo with only GitHub-managed runs (no repository-authored
    workflow at all) must report the same honest 'insufficient evidence'
    signal as a repo with literally zero runs -- not a fabricated clean
    result and not a crash."""
    runs = _runs_data([(1, "dynamic/github-code-scanning/codeql")])

    def side_effect(url, timeout=15):
        if "actions/runs?per_page=" in url:
            return runs
        raise AssertionError(f"should not fetch job detail for a dynamic/ path: {url}")

    with patch("analyze_change._gh_api_get", side_effect=side_effect):
        record = ac.fetch_ci_history("owner/repo", "myservice")
    assert record["available"] is True
    assert record["runs_examined"] == 0
    assert record["service_job_results"] == []
    assert "UNKNOWN / insufficient evidence" in record["historical_signal"]


def test_fetch_ci_history_retrieval_failure_still_produces_unknown_not_a_crash():
    """Confirms the 0.9.0 fail-safe behavior is untouched by this change:
    a transient retrieval failure is still UNKNOWN, not a crash and not
    fabricated history, regardless of which workflow path would have
    matched."""
    with patch("analyze_change._gh_api_get", side_effect=http.client.IncompleteRead(b"partial")):
        record = ac.fetch_ci_history("owner/repo", "myservice")
    assert record["available"] is False
    assert record["historical_signal"] == "UNKNOWN / insufficient evidence"
    assert record["service_job_results"] == []


def test_fetch_ci_history_regression_fixture_saisilinus_shape():
    """Regression fixture modeled on the real failure mode found in the
    prior pilot round: saisilinus/node-express-mongoose-typescript-
    boilerplate's real CI workflow is .github/workflows/node.js.yml, and
    the same repo's real /actions/runs response mixes in a much larger
    number of GitHub-managed dependabot-update entries (37 dynamic
    entries vs. 16 real node.js.yml runs, in the real data). Confirms the
    real workflow's runs are found despite being outnumbered by unrelated
    dynamic runs, and that a job matching the service name inside them is
    discovered -- this is the exact scenario that was previously
    invisible."""
    entries = [(i, "dynamic/dependabot/dependabot-updates") for i in range(1, 38)]
    node_ci_run_ids = list(range(1000, 1016))
    entries += [(run_id, ".github/workflows/node.js.yml") for run_id in node_ci_run_ids]
    runs = _runs_data(entries)
    node_ci_job_urls = {f"https://api.github.com/run/{run_id}/jobs" for run_id in node_ci_run_ids}

    def side_effect(url, timeout=15):
        if "actions/runs?per_page=" in url:
            return runs
        if url in node_ci_job_urls:
            return _jobs_response("Test (node-express-mongoose-typescript-boilerplate)")
        raise AssertionError(f"should not fetch job detail for a dynamic/ path: {url}")

    with patch("analyze_change._gh_api_get", side_effect=side_effect):
        record = ac.fetch_ci_history(
            "saisilinus/node-express-mongoose-typescript-boilerplate",
            "node-express-mongoose-typescript-boilerplate",
        )
    assert record["runs_examined"] == 16  # only the real workflow's runs, not the 37 dependabot entries
    assert record["service_successes"] == 16
    assert record["service_failures"] == 0
    assert "No confirmed CI job failures" in record["historical_signal"]


# ---------------------------------------------------------------------------
# Route-label composition (see pilot/reports/2026-08-29-product-validation-pilot.md,
# Case 2, and docs/decisions/PRODUCT_VALIDATION_GAP_DISPOSITION.md). Mechanism-
# level coverage (mount detection, prefix composition, nesting, slash
# normalization) lives in tests/test_discovery.py; these two tests cover
# requirement 7 (existing impact/test matching keeps working with the
# composed route) and the regression fixture modeled on the real pilot
# failure, both of which need analyze_change.py's own machinery
# (find_test_evidence(), build_impact_assessment()), not discovery.py alone.
# ---------------------------------------------------------------------------

def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _diff_text_for_whole_files(file_line_counts):
    """A minimal unified-diff-shaped diff_text_u0 marking every line of
    each given file as touched -- enough for build_impact_assessment()'s
    overlap check, without constructing a real git diff."""
    lines = []
    for path, count in file_line_counts.items():
        lines.append(f"+++ b/{path}")
        lines.append(f"@@ -1,{count} +1,{count} @@")
    return "\n".join(lines) + "\n"


def test_composed_route_path_feeds_correctly_into_test_evidence_matching(tmp_path):
    """Requirement 7: a test file that calls the real, composed URL is
    found via find_test_evidence() using the composed path -- where the
    bare, uncomposed literal path ("/") is guarded against entirely as
    too generic to search for (analyze_change.py's own existing,
    unchanged robustness guard). This is the exact mechanism that fixed
    Case 2's under-credited test coverage."""
    _write(tmp_path / "app.js", "const api = require('./api.js');\napp.use('/api/v1', api);\n")
    _write(tmp_path / "api.js", "router.get('/', handler);\n")
    _write(tmp_path / "test/api.test.js", "request(app).get('/api/v1');\n")

    mount_map = ac.discovery.build_mount_map(str(tmp_path))
    composed = ac.discovery.compose_route_path(mount_map, "api.js", "/")
    assert composed == "/api/v1"

    hits = ac.find_test_evidence(str(tmp_path), composed)
    assert len(hits) == 1
    assert hits[0]["file"] == "test/api.test.js"
    # The guard on the bare literal path is untouched by this milestone:
    assert ac.find_test_evidence(str(tmp_path), "/") == []


def test_route_label_composition_regression_fixture_matches_real_pilot_case(tmp_path):
    """Regression fixture modeled on the real pilot failure
    (w3cj/express-api-starter, commit 0f9e38d): three distinct real
    routes -- GET / in app.js, GET / in api/index.js (mounted at
    /api/v1), and GET / in api/emojis.js (mounted at /emojis under
    api/index.js, itself mounted at /api/v1) -- previously all rendered
    as an identical "GET /" label. Confirms they are now distinct."""
    app_js = (
        "const api = require('./api/index.js');\n"
        "app.get('/', (req, res) => res.json({ ok: true }));\n"
        "app.use('/api/v1', api);\n"
    )
    api_index_js = (
        "const emojis = require('./emojis.js');\n"
        "router.get('/', (req, res) => res.json({ ok: true }));\n"
        "router.use('/emojis', emojis);\n"
    )
    emojis_js = "router.get('/', (req, res) => res.json(['a']));\n"

    _write(tmp_path / "app.js", app_js)
    _write(tmp_path / "api/index.js", api_index_js)
    _write(tmp_path / "api/emojis.js", emojis_js)
    _write(tmp_path / "package.json", '{"name": "fixture-app"}')

    components = ac.discovery.find_components(str(tmp_path))
    changed_files = ["app.js", "api/index.js", "api/emojis.js"]
    diff_text_u0 = _diff_text_for_whole_files({
        "app.js": len(app_js.splitlines()),
        "api/index.js": len(api_index_js.splitlines()),
        "api/emojis.js": len(emojis_js.splitlines()),
    })
    change = {"changed_files": changed_files, "diff_text_u0": diff_text_u0}

    impact = ac.build_impact_assessment(str(tmp_path), change, components)
    direct = [e for e in impact["affected_entities"] if e["impact_type"] == "DIRECT"]
    entities = sorted(e["entity"] for e in direct)

    assert len(entities) == 3
    assert len(set(entities)) == 3  # no longer collapsed to an identical "GET /"
    assert any(e.endswith("GET /") for e in entities)
    assert any(e.endswith("GET /api/v1") for e in entities)
    assert any(e.endswith("GET /api/v1/emojis") for e in entities)


# ---------------------------------------------------------------------------
# Workspace-aware validation installation (see
# docs/decisions/WORKSPACE_AWARE_INSTALL_DESIGN.md and
# pilot/reports/2026-08-29-product-validation-pilot.md, Case 3).
# Mechanism-level coverage (workspace detection, pattern matching,
# ambiguous/unsupported cases) lives in tests/test_discovery.py; these
# cover run_validation()'s own integration: which directory an install
# actually runs in, and that a genuine install failure there stays a
# safe INCONCLUSIVE outcome, never a fabricated test FAILED.
# ---------------------------------------------------------------------------

def test_run_validation_installs_at_workspace_root_when_component_is_a_declared_member(tmp_path):
    """Positive workspace case, modeled on the real socketio/socket.io
    reproduction: a component nested under packages/ in a repository
    whose root package.json declares it as a workspace member gets its
    dependencies installed AT THE WORKSPACE ROOT, not inside the
    component alone -- while the validation/test command itself still
    runs from the component's own directory, unchanged."""
    (tmp_path / "package.json").write_text(json.dumps({"name": "monorepo", "workspaces": ["packages/*"]}))
    (tmp_path / "packages" / "widgets").mkdir(parents=True)
    selected = _selected_validation()
    selected[0]["target_dir"] = "packages/widgets"

    calls = []

    def side_effect(cmd, cwd=None, **kwargs):
        calls.append((cmd, cwd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok\n", stderr="")

    with patch("analyze_change.subprocess.run", side_effect=side_effect):
        outcomes = ac.run_validation(str(tmp_path), "", selected, npm_install=True)

    install_calls = [c for c in calls if c[0] == "npm install"]
    test_calls = [c for c in calls if c[0] == "npm test"]
    assert len(install_calls) == 1
    assert install_calls[0][1] == str(tmp_path)  # installed at the workspace root, not the component
    assert len(test_calls) == 1
    assert test_calls[0][1] == str(tmp_path / "packages" / "widgets")  # test still runs in the component
    assert outcomes[0]["result"] == "PASSED"
    assert outcomes[0]["install_workspace_root"] == "."  # "." denotes the repo root


def test_run_validation_installs_in_component_dir_when_no_workspace_present(tmp_path):
    """Control / negative-safety case: an ordinary, non-workspace
    repository must install exactly where it always did -- byte-for-byte
    the prior behavior, never redirected to some ancestor just because
    one happens to exist."""
    (tmp_path / "component").mkdir()
    selected = _selected_validation()

    calls = []

    def side_effect(cmd, cwd=None, **kwargs):
        calls.append((cmd, cwd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok\n", stderr="")

    with patch("analyze_change.subprocess.run", side_effect=side_effect):
        outcomes = ac.run_validation(str(tmp_path), "", selected, npm_install=True)

    install_calls = [c for c in calls if c[0] == "npm install"]
    assert len(install_calls) == 1
    assert install_calls[0][1] == str(tmp_path / "component")
    assert "install_workspace_root" not in outcomes[0]


def test_run_validation_workspace_install_failure_is_inconclusive_not_fabricated(tmp_path):
    """Failure case: a genuine workspace-install failure (mirroring the
    real socketio/socket.io reproduction: exit 127, "command not
    found") remains an honest INCONCLUSIVE/INFRASTRUCTURE outcome --
    never fabricated as a real test FAILED result, and the validation
    command is never attempted against dependencies known to be
    unavailable."""
    (tmp_path / "package.json").write_text(json.dumps({"name": "monorepo", "workspaces": ["packages/*"]}))
    (tmp_path / "packages" / "widgets").mkdir(parents=True)
    selected = _selected_validation()
    selected[0]["target_dir"] = "packages/widgets"

    failed_install = subprocess.CompletedProcess(
        args="npm install", returncode=127, stdout="", stderr="sh: prettier: command not found",
    )

    def side_effect(cmd, cwd=None, **kwargs):
        if cmd == "npm install":
            return failed_install
        raise AssertionError("validation command must not run when workspace install fails")

    with patch("analyze_change.subprocess.run", side_effect=side_effect):
        outcomes = ac.run_validation(str(tmp_path), "", selected, npm_install=True)

    assert len(outcomes) == 1
    o = outcomes[0]
    assert o["result"] == "INCONCLUSIVE"
    assert o["result"] != "FAILED"
    assert o["classification"] == "INFRASTRUCTURE (dependency install failed)"
    assert o["install_workspace_root"] == "."


# ---------------------------------------------------------------------------
# Validation-command ancestor fallback (see
# docs/decisions/VALIDATION_ANCESTOR_FALLBACK_DESIGN.md and
# pilot/reports/2026-08-29-milestone-a-generalization.md, Cases 2/3:
# vitejs/vite and apache/superset each have a real changed component with
# no test script of its own, while a real, ancestor-owned test script --
# the one their own real CI actually runs -- was never discovered).
# Mechanism-level ancestor-walk coverage (nearest-wins, sibling exclusion,
# repository-root fallback) lives in test_discovery.py; these cover
# build_validation_decision()'s own integration: reason text, target_dir
# wiring, and that existing behavior is completely unaffected when a
# component already has a valid local command.
# ---------------------------------------------------------------------------

def _validation_risk():
    return {
        "structural_exposure": {"caller_services": []},
        "has_cross_service_validation": False,
        "direct_test_coverage": True,
    }


def test_build_validation_decision_uses_component_local_test_script_unchanged(tmp_path):
    """Baseline/regression: a component with its own test script is
    selected exactly as before this milestone -- own directory, no
    ancestor-fallback fields, unchanged reason wording."""
    _write(tmp_path / "widgets" / "package.json", json.dumps({"name": "widgets", "scripts": {"test": "jest"}}))
    components = ac.discovery.find_components(str(tmp_path))
    change = {"changed_files": ["widgets/index.js"]}

    decision = ac.build_validation_decision(str(tmp_path), change, _validation_risk(), components)

    assert len(decision["selected_validations"]) == 1
    v = decision["selected_validations"][0]
    assert v["target"] == "widgets"
    assert v["target_dir"] == "widgets"
    assert v["command"] == "npm test"
    assert "validated_via_ancestor" not in v
    assert decision["rejected_validations"] == []
    assert "has no test script of its own" not in v["decision_reason"]


def test_build_validation_decision_falls_back_to_nearest_ancestor(tmp_path):
    """One-level (nearest-ancestor) fallback: the changed component has
    no test script, but its nearest ancestor component does -- that
    ancestor's directory and script are selected, and the fallback is
    disclosed in both the machine-readable field and the reason text."""
    _write(tmp_path / "package.json", json.dumps({"name": "monorepo"}))
    _write(
        tmp_path / "packages" / "frontend" / "package.json",
        json.dumps({"name": "frontend", "scripts": {"test": "jest"}}),
    )
    _write(
        tmp_path / "packages" / "frontend" / "plugins" / "widgets" / "package.json",
        json.dumps({"name": "widgets", "scripts": {}}),
    )
    components = ac.discovery.find_components(str(tmp_path))
    change = {"changed_files": ["packages/frontend/plugins/widgets/index.tsx"]}

    decision = ac.build_validation_decision(str(tmp_path), change, _validation_risk(), components)

    assert len(decision["selected_validations"]) == 1
    v = decision["selected_validations"][0]
    assert v["target"] == "widgets"  # still attributed to the changed component
    assert v["target_dir"] == "packages/frontend"  # but runs where the real test script lives
    assert v["command"] == "npm test"
    assert v["validated_via_ancestor"] == "packages/frontend"
    assert "has no test script of its own" in v["decision_reason"]
    assert "packages/frontend" in v["decision_reason"]
    assert decision["rejected_validations"] == []


def test_build_validation_decision_falls_back_to_repository_root_where_appropriate(tmp_path):
    """Real vitejs/vite shape: the changed component has no test script,
    no intermediate ancestor has one either, but the repository root
    does -- the repository root is used (target_dir == ""), not treated
    as unavailable."""
    _write(tmp_path / "package.json", json.dumps({"name": "monorepo", "scripts": {"test": "pnpm test-unit"}}))
    _write(
        tmp_path / "packages" / "vite" / "package.json",
        json.dumps({"name": "vite", "scripts": {"build": "rolldown"}}),
    )
    components = ac.discovery.find_components(str(tmp_path))
    change = {"changed_files": ["packages/vite/src/node/server/pluginContainer.ts"]}

    decision = ac.build_validation_decision(str(tmp_path), change, _validation_risk(), components)

    assert len(decision["selected_validations"]) == 1
    v = decision["selected_validations"][0]
    assert v["target"] == "vite"
    assert v["target_dir"] == ""  # the repository root
    assert v["validated_via_ancestor"] == "."
    assert "the repository root" in v["decision_reason"]
    assert decision["rejected_validations"] == []


def test_build_validation_decision_rejects_when_no_ancestor_has_a_test_script(tmp_path):
    """No applicable ancestor anywhere (including the repository root
    itself) has a test script -- existing "no validation available"
    behavior is preserved exactly: nothing selected, a rejection
    recorded, which final_recommendation() turns into ESCALATE."""
    _write(tmp_path / "package.json", json.dumps({"name": "monorepo"}))
    _write(tmp_path / "packages" / "widgets" / "package.json", json.dumps({"name": "widgets", "scripts": {}}))
    components = ac.discovery.find_components(str(tmp_path))
    change = {"changed_files": ["packages/widgets/index.js"]}

    decision = ac.build_validation_decision(str(tmp_path), change, _validation_risk(), components)

    assert decision["selected_validations"] == []
    assert len(decision["rejected_validations"]) == 1
    r = decision["rejected_validations"][0]
    assert r["target"] == "widgets"
    assert "No 'test' script found" in r["decision_reason"]

    outcomes = []
    result, _ = ac.final_recommendation(_risk(), outcomes, decision)
    assert result == "ESCALATE"


def test_build_validation_decision_does_not_select_a_sibling_components_script(tmp_path):
    """A sibling component's real test script must never be selected for
    a changed component just because it exists somewhere in the
    repository -- only genuine ancestors are eligible. With no genuine
    ancestor available, this must reject exactly like the no-ancestor
    case above, not silently borrow the sibling's script."""
    _write(tmp_path / "package.json", json.dumps({"name": "monorepo"}))
    _write(tmp_path / "packages" / "widgets" / "package.json", json.dumps({"name": "widgets", "scripts": {}}))
    _write(
        tmp_path / "packages" / "other" / "package.json",
        json.dumps({"name": "other", "scripts": {"test": "mocha"}}),
    )
    components = ac.discovery.find_components(str(tmp_path))
    change = {"changed_files": ["packages/widgets/index.js"]}

    decision = ac.build_validation_decision(str(tmp_path), change, _validation_risk(), components)

    assert decision["selected_validations"] == []
    assert len(decision["rejected_validations"]) == 1
    assert decision["rejected_validations"][0]["target"] == "widgets"
