from pathlib import Path
from typing import Any

from traceval.analyze.cluster import JaccardClusterer
from traceval.analyze.coverage import compute_coverage
from traceval.analyze.outcomes import label_trace, load_user_rules
from traceval.analyze.report import render_report
from traceval.store import TraceStore


def run_analysis(
    db_path: Path,
    rules_path: Path | None = None,
    evals_dir: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    store = TraceStore(db_path)
    try:
        # 1. Load user rules if any
        user_rules = None
        if rules_path:
            user_rules = load_user_rules(rules_path)

        # 2. Label all traces
        traces = list(store.list_traces())
        for trace in traces:
            outcome = label_trace(trace, user_rules=user_rules)
            trace.outcome = outcome
            store.save_trace(trace)

        # 3. Fetch fresh labeled traces
        labeled_traces = list(store.list_traces())

        # 4. Cluster traces
        clusterer = JaccardClusterer()
        clusters = clusterer.cluster(labeled_traces)

        # 5. Compute coverage of clusters against existing evals
        coverage = compute_coverage(clusters, evals_dir, labeled_traces)

        # 6. Render reports if output_dir is provided
        summary = {
            "total_traces": len(labeled_traces),
            "outcomes": {},
            "clusters": [],
        }

        # Populate summary outcomes counts
        outcome_counts: dict[str, int] = {}
        for t in labeled_traces:
            lbl = t.outcome.label if t.outcome else "unknown"
            outcome_counts[lbl] = outcome_counts.get(lbl, 0) + 1
        summary["outcomes"] = outcome_counts

        summary["clusters"] = [
            {
                "id": c.id,
                "name": c.name,
                "tool_signature": c.tool_signature,
                "top_terms": c.top_terms,
                "trace_count": len(c.trace_ids),
                "trace_ids": c.trace_ids,
                "coverage_count": coverage.get(c.id, 0),
            }
            for c in clusters
        ]

        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            html_path = output_dir / "report.html"
            render_report(summary, coverage, html_path)

        return summary
    finally:
        store.close()
