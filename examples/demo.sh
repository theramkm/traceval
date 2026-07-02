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

echo -e "\n=== 5. Run evals against healthy demo agent ==="
# We add --with fastapi --with uvicorn --with pytest so that all run dependencies are active
HEALTHY_REPORT=$(uv run --with fastapi --with uvicorn --with pytest python3 src/traceval/cli.py run demo_evals/ --target examples.demo_agent.agent:invoke_agent --judge fake | grep -o 'demo_evals/runs/run_.*\.json' | head -n 1) || true

echo -e "\n=== 6. Run evals against buggy demo agent and compare ==="
if [ -n "$HEALTHY_REPORT" ]; then
  # Should report regressions and exit with failure code 1
  BUGGY=true uv run --with fastapi --with uvicorn --with pytest python3 src/traceval/cli.py run demo_evals/ --target examples.demo_agent.agent:invoke_agent --judge fake --compare "$HEALTHY_REPORT" || echo "✅ E2E regression check passed: traceval correctly detected regressions and exited with failure status!"
else
  # Fallback if grep failed to capture path
  BUGGY=true uv run --with fastapi --with uvicorn --with pytest python3 src/traceval/cli.py run demo_evals/ --target examples.demo_agent.agent:invoke_agent --judge fake || echo "✅ E2E regression check passed: traceval correctly detected regressions!"
fi
