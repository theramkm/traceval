# ruff: noqa: E501
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path


def generate_traces_file(output_path: Path) -> None:
    # Deterministic output: keeps the committed synthetic_traces.jsonl stable
    # across regenerations (and cluster counts stable in tests).
    random.seed(42)

    traces = []

    # Fixed base timestamp (see determinism note above)
    base_time = datetime(2026, 6, 30, 12, 0, 0, tzinfo=UTC)

    # 1. Generate 120 success traces
    # Orders, refunds, KB searches
    for i in range(120):
        trace_id = f"tr-success-{i:03d}"
        started_at = base_time + timedelta(minutes=i * 5)
        ended_at = started_at + timedelta(seconds=random.uniform(0.5, 2.5))

        category = random.choice(["order", "refund", "kb", "fallback"])
        if category == "order":
            order_id = random.randint(10000, 99999)
            task_input = f"Where is order {order_id}?"
            final_output = f"Your order {order_id} is currently in transit."
            steps = [
                {
                    "index": 0,
                    "kind": "tool",
                    "tool": {
                        "span_id": f"span-o-{i}",
                        "name": "order_lookup",
                        "arguments_json": f'{{"order_id": "{order_id}"}}',
                        "output": "status: transit",
                        "latency_ms": random.uniform(100, 300),
                    },
                }
            ]
        elif category == "refund":
            task_input = "Refund my charge via stripe"
            final_output = "Refund of $50 has been successfully processed via Stripe."
            steps = [
                {
                    "index": 0,
                    "kind": "tool",
                    "tool": {
                        "span_id": f"span-r-{i}",
                        "name": "stripe_lookup",
                        "arguments_json": '{"amount": 50}',
                        "output": "status: success",
                        "latency_ms": random.uniform(200, 500),
                    },
                }
            ]
        elif category == "kb":
            task_input = "Search knowledge base for credential updates"
            final_output = "Found answer in documentation: update your credentials."
            steps = [
                {
                    "index": 0,
                    "kind": "tool",
                    "tool": {
                        "span_id": f"span-k-{i}",
                        "name": "kb_search",
                        "arguments_json": '{"query": "credentials"}',
                        "output": "found: credential update docs",
                        "latency_ms": random.uniform(150, 400),
                    },
                }
            ]
        else:
            task_input = "Just say hi"
            final_output = (
                "Hello! I can help you with order lookups, refunds, or searches."
            )
            steps = []

        traces.append(
            {
                "trace_id": trace_id,
                "source": "generic",
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "task_input": task_input,
                "final_output": final_output,
                "steps": steps,
            }
        )

    # 2. Generate 30 tool error traces
    for i in range(30):
        trace_id = f"tr-toolerr-{i:03d}"
        started_at = base_time + timedelta(hours=10) + timedelta(minutes=i * 5)
        ended_at = started_at + timedelta(seconds=random.uniform(0.3, 1.5))

        task_input = "Refund of $500 on stripe"
        final_output = "Error: Stripe refund lookup service unavailable."
        steps = [
            {
                "index": 0,
                "kind": "tool",
                "tool": {
                    "span_id": f"span-te-{i}",
                    "name": "stripe_lookup",
                    "arguments_json": '{"amount": 500}',
                    "output": None,
                    "error": "HTTP 503 Service Unavailable",
                    "latency_ms": random.uniform(100, 200),
                },
            }
        ]

        traces.append(
            {
                "trace_id": trace_id,
                "source": "generic",
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "task_input": task_input,
                "final_output": final_output,
                "steps": steps,
            }
        )

    # 3. Generate 20 loop traces
    for i in range(20):
        trace_id = f"tr-loop-{i:03d}"
        started_at = base_time + timedelta(hours=15) + timedelta(minutes=i * 5)
        ended_at = started_at + timedelta(seconds=random.uniform(2.0, 5.0))

        task_input = "repeated tool execution check"
        final_output = "Failed execution due to system loop."

        # Loop: same tool name called with identical arguments_json >= 3 times consecutively
        steps = []
        for s in range(4):
            steps.append(
                {
                    "index": s,
                    "kind": "tool",
                    "tool": {
                        "span_id": f"span-loop-{i}-{s}",
                        "name": "order_lookup",
                        "arguments_json": '{"order_id": "12345"}',
                        "output": "status: pending",
                        "latency_ms": 100,
                    },
                }
            )

        traces.append(
            {
                "trace_id": trace_id,
                "source": "generic",
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "task_input": task_input,
                "final_output": final_output,
                "steps": steps,
            }
        )

    # 4. Generate 15 timeout traces
    for i in range(15):
        trace_id = f"tr-timeout-{i:03d}"
        started_at = base_time + timedelta(hours=20) + timedelta(minutes=i * 5)

        # Timeout: ended_at missing
        task_input = "timeout hang task"
        final_output = None

        traces.append(
            {
                "trace_id": trace_id,
                "source": "generic",
                "started_at": started_at.isoformat(),
                "ended_at": None,
                "task_input": task_input,
                "final_output": final_output,
                "steps": [],
            }
        )

    # 5. Generate 15 validation error traces
    for i in range(15):
        trace_id = f"tr-valerr-{i:03d}"
        started_at = base_time + timedelta(hours=22) + timedelta(minutes=i * 5)
        ended_at = started_at + timedelta(seconds=random.uniform(0.5, 1.5))

        task_input = "validation check query"
        # validation signature matching
        final_output = "validation_error: Field required [type=missing]"

        traces.append(
            {
                "trace_id": trace_id,
                "source": "generic",
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "task_input": task_input,
                "final_output": final_output,
                "steps": [],
            }
        )

    # Write all traces to file
    with open(output_path, "w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(t) + "\n")

    print(f"✅ Generated {len(traces)} synthetic traces → {output_path}")


if __name__ == "__main__":
    out = Path(__file__).parent / "synthetic_traces.jsonl"
    generate_traces_file(out)
