#!/bin/bash
# Regenerates every sample-output block in README.md, plus
# docs/img/report.png, from real command runs so the docs cannot drift.
# Run from anywhere; paste the printed sections into README.md verbatim.
set -e

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

tv() { uv run --project "$ROOT" traceval "$@"; }

uv run --project "$ROOT" python3 -c "
from pathlib import Path
from traceval.demo.traces import generate_traces_file
generate_traces_file(Path('traces.jsonl'))
" >/dev/null

echo "=== ingest ==="
tv ingest traces.jsonl -o traces.db

echo
echo "=== analyze ==="
tv analyze traces.db -o analysis

echo
echo "=== generate ==="
tv generate traces.db -o evals --include-failures

echo
echo "=== run (healthy demo agent) ==="
tv run evals --target traceval.demo.agent:invoke_agent --judge fake || true

echo
echo "=== calibrate (example labels: 7x pass, 1x fail) ==="
REPORT=$(ls -t evals/runs/run_*.json | head -1)
printf 'y\ny\ny\ny\nn\ny\ny\ny\n' | tv calibrate "$REPORT" --sample 8 | tail -16

echo
echo "=== screenshot -> docs/img/report.png ==="
# Re-analyze with --evals so the report shows populated eval coverage
tv analyze traces.db --evals evals -o analysis >/dev/null
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ -x "$CHROME" ]; then
  "$CHROME" --headless --disable-gpu \
    --screenshot="$ROOT/docs/img/report.png" \
    --window-size=1280,860 --hide-scrollbars \
    "file://$WORK/analysis/report.html" 2>/dev/null
  echo "wrote $ROOT/docs/img/report.png"
else
  echo "Chrome not found; screenshot skipped"
fi
