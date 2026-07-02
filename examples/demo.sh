#!/bin/bash
# traceval e2e quickstart demo script
set -e

echo "=== 1. Generate synthetic traces ==="
python3 examples/make_traces.py

echo -e "\n=== 2. Ingest traces into SQLite ==="
rm -f demo_traces.db
uv run python3 src/traceval/cli.py ingest examples/synthetic_traces.jsonl -o demo_traces.db

echo -e "\n=== 3. Analyze traces (labeling, clustering, outcomes) ==="
uv run python3 src/traceval/cli.py analyze demo_traces.db -o demo_analysis/

echo -e "\n=== 4. Generate eval suite ==="
rm -rf demo_evals/
uv run python3 src/traceval/cli.py generate demo_traces.db -o demo_evals/ --include-failures

echo -e "\n=== 5. Run evals against healthy demo agent (must pass) ==="
# We add --with fastapi --with uvicorn --with pytest so that all run dependencies are active
# set -e enforces the core promise here: the healthy agent passes its own suite (exit 0)
uv run --with fastapi --with uvicorn --with pytest python3 src/traceval/cli.py run demo_evals/ --target examples.demo_agent.core:invoke_agent --judge fake
HEALTHY_REPORT=$(ls -t demo_evals/runs/run_*.json | head -n 1)

echo -e "\n=== 6. Run evals against buggy demo agent and compare (must fail) ==="
if BUGGY=true uv run --with fastapi --with uvicorn --with pytest python3 src/traceval/cli.py run demo_evals/ --target examples.demo_agent.core:invoke_agent --judge fake --compare "$HEALTHY_REPORT"; then
  echo "❌ E2E regression check FAILED: buggy agent passed the suite!"
  exit 1
else
  echo "✅ E2E regression check passed: traceval correctly detected regressions and exited with failure status!"
fi
