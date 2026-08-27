"""
Artifact history: preserves every ImpactTestAI execution as an immutable,
independently traceable historical record.

Scope (see slice/ARTIFACT_HISTORY_DESIGN.md): run identity, artifact
storage/layout, and cross-artifact consistency only. Does not touch
design8.md, design9.md, the risk/decision policy, or architecture
discovery -- this module has no knowledge of RiskAssessment, probability,
or any decision rule; it only stores what analyze_change.py already
computed.
"""
import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone


def generate_run_id():
    """Timestamp + random suffix -- sortable and human-readable, but the
    random component (not the timestamp) is what actually guarantees
    uniqueness, so two executions started in the same second (or two
    concurrent CI jobs writing to shared storage) never collide. No
    coordination, locking, or shared counter required. See design doc for
    why this was chosen over sequential numbering."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


_GITHUB_REMOTE_RE = re.compile(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?/?$")


def resolve_identity(repo, github_repo=None):
    """Returns (organization, repository, repository_url). Priority order:

      1. --github-repo owner/repo, if given (already an existing flag used
         for CI-history fetching).
      2. `git remote get-url origin` in the target repo, if it parses as a
         GitHub remote -- repository_url is reported exactly as git gives
         it, not reconstructed.
      3. Fallback: organization="local", repository=<basename of repo's
         absolute path>, repository_url=None. An honest "no remote
         identity available" outcome, not a guess.
    """
    if github_repo and "/" in github_repo:
        org, name = github_repo.split("/", 1)
        return org, name, f"https://github.com/{github_repo}"

    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo, capture_output=True, text=True, timeout=10,
        )
        remote_url = result.stdout.strip()
        m = _GITHUB_REMOTE_RE.search(remote_url) if remote_url else None
        if m:
            return m.group(1), m.group(2), remote_url
    except (OSError, subprocess.SubprocessError):
        pass

    return "local", os.path.basename(os.path.abspath(repo).rstrip("/")), None


def resolve_sha(repo, ref):
    """Resolves `ref` (a branch name, "HEAD", "origin/main", or an already-
    resolved SHA) to its exact commit SHA via `git rev-parse`. Falls back
    to the raw ref string, clearly unresolved, if git can't resolve it --
    an honest degradation, not a crash, consistent with this project's
    existing insufficient-evidence philosophy."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", ref],
            cwd=repo, capture_output=True, text=True, timeout=10,
        )
        sha = result.stdout.strip()
        if result.returncode == 0 and sha:
            return sha
    except (OSError, subprocess.SubprocessError):
        pass
    return f"UNRESOLVED:{ref}"


def write_run_artifacts(artifacts_root, organization, repository, run_id, report_text, audit_record, metadata):
    """Writes report.md, audit.json, and metadata.json together under
    <artifacts_root>/<organization>/<repository>/<run_id>/. Creates the run
    directory with exist_ok=False: since run_id is generated fresh
    in-memory before any file exists, this raises rather than silently
    overwriting a prior run's artifacts in the (practically impossible)
    event of a collision -- the mechanism that enforces "never overwrite
    history."

    audit_record gains a "run_id" key (mutated in place) so audit.json is
    self-identifying even if separated from the other two files;
    metadata's own run_id field serves the same purpose for metadata.json.
    Returns the run directory path."""
    run_dir = os.path.join(artifacts_root, organization, repository, run_id)
    os.makedirs(run_dir, exist_ok=False)

    audit_record["run_id"] = run_id

    with open(os.path.join(run_dir, "report.md"), "w") as f:
        f.write(report_text)
    with open(os.path.join(run_dir, "audit.json"), "w") as f:
        json.dump(audit_record, f, indent=2)
    with open(os.path.join(run_dir, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    return run_dir
