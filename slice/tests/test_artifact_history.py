"""
History validation tests for the Artifact History & Reproducibility
milestone (see slice/ARTIFACT_HISTORY_DESIGN.md).

Two layers:
  - Unit tests against artifact_history.py directly (run_id generation,
    identity resolution, immutability enforcement).
  - End-to-end tests that invoke analyze_change.py as a subprocess (the
    same way a pilot user / GitHub Actions workflow does) against a
    synthetic, portable git fixture repo -- not a real cloned repository,
    for the same reason test_known_repos_regression.py uses synthetic
    fixtures: portability for CI.
"""
import json
import os
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import artifact_history  # noqa: E402

ANALYZE_SCRIPT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "analyze_change.py"))


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _make_repo(path, remote_url=None):
    """A minimal, portable synthetic Express repo -- just enough for
    analyze_change.py to find a real route-level change to report on."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    (path / "package.json").write_text(json.dumps({"name": "widget-service"}))
    (path / "routes.js").write_text('app.get("/health", (req, res) => { res.send("ok"); });\n')
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "initial")
    if remote_url:
        _git(path, "remote", "add", "origin", remote_url)
    return path


def _touch_change(repo_path):
    """Makes an uncommitted, analyzable change to the route file."""
    (repo_path / "routes.js").write_text(
        'app.get("/health", (req, res) => { res.send("ok-v2"); });\n'
    )


def _run_analyzer(repo_path, artifacts_root, against="HEAD", out_name="report.md"):
    out_path = artifacts_root.parent / out_name
    result = subprocess.run(
        [
            sys.executable, ANALYZE_SCRIPT, str(repo_path),
            "--against", against, "--no-run",
            "--artifacts-root", str(artifacts_root),
            "--out", str(out_path),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"analyzer failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    return result


def _find_run_dirs(artifacts_root):
    """All run directories under artifacts_root, regardless of
    organization/repository -- <artifacts_root>/*/*/<run_id>/."""
    if not artifacts_root.exists():
        return []
    runs = []
    for org_dir in artifacts_root.iterdir():
        if not org_dir.is_dir():
            continue
        for repo_dir in org_dir.iterdir():
            if not repo_dir.is_dir():
                continue
            runs.extend(p for p in repo_dir.iterdir() if p.is_dir())
    return sorted(runs)


# ---------------------------------------------------------------------------
# Unit tests: artifact_history.py primitives
# ---------------------------------------------------------------------------

def test_generate_run_id_is_unique_across_calls():
    ids = {artifact_history.generate_run_id() for _ in range(20)}
    assert len(ids) == 20


def test_generate_run_id_not_timestamp_alone():
    """Two IDs generated in the same second must still differ -- the
    random suffix, not the timestamp, is what guarantees uniqueness."""
    a = artifact_history.generate_run_id()
    b = artifact_history.generate_run_id()
    assert a != b
    # Same timestamp prefix is plausible (same second); the full IDs must
    # still differ because of the random suffix.
    assert a.split("-")[-1] != b.split("-")[-1]


def test_resolve_identity_uses_github_repo_flag_first():
    org, repo, url = artifact_history.resolve_identity("/nonexistent/path/does/not/matter", "acme/widgets")
    assert (org, repo, url) == ("acme", "widgets", "https://github.com/acme/widgets")


def test_resolve_identity_falls_back_to_git_remote(tmp_path):
    repo_path = _make_repo(tmp_path / "repo", remote_url="git@github.com:some-org/some-repo.git")
    org, repo, url = artifact_history.resolve_identity(str(repo_path))
    assert org == "some-org"
    assert repo == "some-repo"
    assert url == "git@github.com:some-org/some-repo.git"


def test_resolve_identity_falls_back_to_local_basename_without_remote(tmp_path):
    repo_path = _make_repo(tmp_path / "my-local-widget-repo")
    org, repo, url = artifact_history.resolve_identity(str(repo_path))
    assert org == "local"
    assert repo == "my-local-widget-repo"
    assert url is None


def test_resolve_sha_resolves_head(tmp_path):
    repo_path = _make_repo(tmp_path / "repo")
    sha = artifact_history.resolve_sha(str(repo_path), "HEAD")
    assert len(sha) == 40
    assert all(c in "0123456789abcdef" for c in sha)


def test_write_run_artifacts_never_overwrites_a_collision(tmp_path):
    artifacts_root = tmp_path / "artifacts"
    run_id = artifact_history.generate_run_id()
    artifact_history.write_run_artifacts(
        str(artifacts_root), "org", "repo", run_id, "report one", {"x": 1}, {"y": 1},
    )
    with pytest.raises(FileExistsError):
        artifact_history.write_run_artifacts(
            str(artifacts_root), "org", "repo", run_id, "report TWO -- should never land", {"x": 2}, {"y": 2},
        )
    # The original content must be completely unaffected by the failed
    # second attempt.
    report = (artifacts_root / "org" / "repo" / run_id / "report.md").read_text()
    assert report == "report one"


def test_write_run_artifacts_injects_run_id_into_audit_record(tmp_path):
    artifacts_root = tmp_path / "artifacts"
    run_id = artifact_history.generate_run_id()
    audit_record = {"something": "else"}
    artifact_history.write_run_artifacts(
        str(artifacts_root), "org", "repo", run_id, "report", audit_record, {"run_id": run_id},
    )
    on_disk = json.loads((artifacts_root / "org" / "repo" / run_id / "audit.json").read_text())
    assert on_disk["run_id"] == run_id
    assert on_disk["something"] == "else"


# ---------------------------------------------------------------------------
# End-to-end tests: invoking analyze_change.py the way a pilot user does
# ---------------------------------------------------------------------------

def test_two_executions_receive_different_run_ids(tmp_path):
    repo_path = _make_repo(tmp_path / "repo")
    _touch_change(repo_path)
    artifacts_root = tmp_path / "artifacts"

    _run_analyzer(repo_path, artifacts_root, out_name="r1.md")
    time.sleep(1.1)  # ensure a different timestamp prefix too, for a stronger check
    _run_analyzer(repo_path, artifacts_root, out_name="r2.md")

    runs = _find_run_dirs(artifacts_root)
    assert len(runs) == 2
    assert runs[0].name != runs[1].name


def test_repeated_analysis_of_identical_commit_does_not_overwrite_or_deduplicate(tmp_path):
    """Run A: repo=X, head=ABC, base=DEF. Run B: repo=X, head=ABC, base=DEF
    (same repo, same uncommitted change, same --against ref). Both must
    survive independently -- this is the exact scenario needed to detect
    future nondeterminism, and deduplication would defeat that purpose."""
    repo_path = _make_repo(tmp_path / "repo")
    _touch_change(repo_path)
    artifacts_root = tmp_path / "artifacts"

    _run_analyzer(repo_path, artifacts_root, against="HEAD", out_name="a.md")
    _run_analyzer(repo_path, artifacts_root, against="HEAD", out_name="b.md")

    runs = _find_run_dirs(artifacts_root)
    assert len(runs) == 2, "identical-input executions must not be deduplicated"

    metas = [json.loads((r / "metadata.json").read_text()) for r in runs]
    # Same repository state analyzed both times...
    assert metas[0]["head_sha"] == metas[1]["head_sha"]
    assert metas[0]["base_sha"] == metas[1]["base_sha"]
    assert metas[0]["tool_version"] == metas[1]["tool_version"]
    assert metas[0]["policy_version"] == metas[1]["policy_version"]
    # ...but two distinct, traceable executions.
    assert metas[0]["run_id"] != metas[1]["run_id"]


def test_earlier_artifact_remains_unchanged_after_a_later_execution(tmp_path):
    repo_path = _make_repo(tmp_path / "repo")
    _touch_change(repo_path)
    artifacts_root = tmp_path / "artifacts"

    _run_analyzer(repo_path, artifacts_root, out_name="a.md")
    runs = _find_run_dirs(artifacts_root)
    assert len(runs) == 1
    first_run_dir = runs[0]
    first_report_before = (first_run_dir / "report.md").read_text()
    first_audit_before = (first_run_dir / "audit.json").read_text()
    first_metadata_before = (first_run_dir / "metadata.json").read_text()

    # A second, different execution against a DIFFERENT change.
    (repo_path / "routes.js").write_text(
        'app.get("/health", (req, res) => { res.send("v3"); });\n'
        'app.post("/widgets", (req, res) => { res.send("created"); });\n'
    )
    _run_analyzer(repo_path, artifacts_root, out_name="b.md")

    runs_after = _find_run_dirs(artifacts_root)
    assert len(runs_after) == 2

    assert (first_run_dir / "report.md").read_text() == first_report_before
    assert (first_run_dir / "audit.json").read_text() == first_audit_before
    assert (first_run_dir / "metadata.json").read_text() == first_metadata_before


def test_metadata_contains_all_required_identity_and_decision_fields(tmp_path):
    repo_path = _make_repo(tmp_path / "repo", remote_url="https://github.com/acme-co/widget-service.git")
    _touch_change(repo_path)
    artifacts_root = tmp_path / "artifacts"

    _run_analyzer(repo_path, artifacts_root)
    run_dir = _find_run_dirs(artifacts_root)[0]
    metadata = json.loads((run_dir / "metadata.json").read_text())

    required_fields = {
        "run_id", "organization", "repository", "repository_url",
        "head_sha", "base_sha", "tool_version", "policy_version",
        "started_at", "completed_at", "decision", "risk_level",
    }
    assert required_fields <= metadata.keys()

    # Repository identity actually recorded, not placeholders.
    assert metadata["organization"] == "acme-co"
    assert metadata["repository"] == "widget-service"
    assert metadata["repository_url"] == "https://github.com/acme-co/widget-service.git"

    # head/base SHA recorded as real 40-char git SHAs, not timestamps or refs.
    assert len(metadata["head_sha"]) == 40
    assert len(metadata["base_sha"]) == 40
    assert metadata["head_sha"] == metadata["base_sha"]  # --against HEAD in this test

    # Tool/policy version recorded, and match the actual current constants
    # (not hard-coded example versions).
    import analyze_change as ac
    assert metadata["tool_version"] == ac.TOOL_VERSION
    assert metadata["policy_version"] == ac.POLICY_VERSION

    # Timestamps recorded and ordered sensibly.
    assert metadata["started_at"] <= metadata["completed_at"]

    # Decision and risk level recorded with real values from this run.
    assert metadata["decision"] in ("ACCEPT", "ESCALATE", "REQUIRE_ADDITIONAL_VALIDATION")
    assert metadata["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def test_report_audit_and_metadata_belong_to_the_same_run(tmp_path):
    """Prevents the exact failure mode called out in the milestone:
    report.md=A, audit.json=B, metadata.json=C from different runs."""
    repo_path = _make_repo(tmp_path / "repo")
    _touch_change(repo_path)
    artifacts_root = tmp_path / "artifacts"

    _run_analyzer(repo_path, artifacts_root, out_name="a.md")
    time.sleep(1.1)
    _run_analyzer(repo_path, artifacts_root, out_name="b.md")

    for run_dir in _find_run_dirs(artifacts_root):
        run_id_from_dirname = run_dir.name
        metadata = json.loads((run_dir / "metadata.json").read_text())
        audit = json.loads((run_dir / "audit.json").read_text())
        report_text = (run_dir / "report.md").read_text()

        assert metadata["run_id"] == run_id_from_dirname
        assert audit["run_id"] == run_id_from_dirname
        assert f"Run ID: `{run_id_from_dirname}`" in report_text

        # And the decision/risk_level agree between metadata and audit --
        # not just present, but consistent with each other for this run.
        assert metadata["decision"] == audit["recommendation"]["decision"]
        assert metadata["risk_level"] == audit["risk"]["risk_level"]


def test_different_base_commits_are_recorded_distinctly(tmp_path):
    repo_path = _make_repo(tmp_path / "repo")
    first_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True,
    ).stdout.strip()

    (repo_path / "routes.js").write_text(
        'app.get("/health", (req, res) => { res.send("ok"); });\n'
        'app.get("/status", (req, res) => { res.send("up"); });\n'
    )
    _git(repo_path, "add", ".")
    _git(repo_path, "commit", "-q", "-m", "add status route")

    _touch_change(repo_path)
    artifacts_root = tmp_path / "artifacts"
    _run_analyzer(repo_path, artifacts_root, against=first_commit, out_name="a.md")

    run_dir = _find_run_dirs(artifacts_root)[0]
    metadata = json.loads((run_dir / "metadata.json").read_text())
    assert metadata["base_sha"] == first_commit
    assert metadata["head_sha"] != first_commit


def test_no_repository_specific_rules_in_artifact_history_module():
    """Overfitting/special-case guard: artifact_history.py must contain no
    reference to any specific repository, organization, or filename used
    anywhere in this project's testing history."""
    source = open(os.path.join(os.path.dirname(__file__), "..", "artifact_history.py")).read()
    for needle in (
        "social-media-mini", "user-management-app", "bulletproof-nodejs",
        "node-express-boilerplate", "fastify-api", "express-typescript",
        "nestjs-realworld", "spacex", "node-fastify-api-boilerplate",
    ):
        assert needle not in source
