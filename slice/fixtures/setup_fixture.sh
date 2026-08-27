#!/usr/bin/env bash
# Builds a throwaway git repository from the committed fixture source
# (sample-service/) in a temp directory, commits a baseline, then applies
# a small, deterministic "change" as an UNCOMMITTED diff -- exactly the
# state analyze_change.py expects to analyze (like a real PR under
# review). Prints the temp directory path on stdout.
#
# This exists so the pilot CI workflow can exercise the analyzer
# end-to-end without depending on any external repository or network
# access -- see .github/workflows/pilot-ci.yml.
set -euo pipefail

FIXTURE_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sample-service"
WORKDIR="$(mktemp -d)"

cp -R "$FIXTURE_SRC"/. "$WORKDIR"/
cd "$WORKDIR"

git init -q
git config user.email "pilot-ci@example.invalid"
git config user.name "Pilot CI"
git add -A
git commit -q -m "baseline fixture commit"

# Apply the "change" under review: introduces a risk indicator (new
# in-memory state) into the /widgets handler, deliberately with no
# dependent caller and no direct test coverage -- exercises different
# code paths than the real social-media-mini demonstration change.
python3 - "$WORKDIR/services/widget-service/server.js" <<'PY'
import sys
path = sys.argv[1]
with open(path) as f:
    text = f.read()
text = text.replace(
    'app.get("/widgets", (req, res) => {\n  res.json({ widgets: [] });\n});',
    'const widgetCache = new Map();\napp.get("/widgets", (req, res) => {\n  res.json({ widgets: [] });\n});',
)
with open(path, "w") as f:
    f.write(text)
PY

echo "$WORKDIR"
