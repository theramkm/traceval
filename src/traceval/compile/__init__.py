from pathlib import Path

from traceval.analyze.cluster import JaccardClusterer
from traceval.analyze.outcomes import label_trace
from traceval.compile.cases import select_and_redact_cases
from traceval.compile.emit_pytest import emit_pytest_suite
from traceval.compile.emit_yaml import emit_yaml_suite
from traceval.compile.rubrics import emit_rubrics
from traceval.store import TraceStore


def generate_evals(
    db_path: Path,
    output_dir: Path,
    per_cluster: int = 3,
    include_failures: bool = False,
    redact_hook_str: str | None = None,
) -> tuple[int, int]:
    store = TraceStore(db_path)
    try:
        traces = list(store.list_traces())

        # Ensure outcome and rules are run
        for trace in traces:
            if not trace.outcome:
                trace.outcome = label_trace(trace)

        clusterer = JaccardClusterer()
        clusters = clusterer.cluster(traces)

        cases = select_and_redact_cases(
            clusters,
            traces,
            per_cluster=per_cluster,
            include_failures=include_failures,
            redact_hook_str=redact_hook_str,
        )

        # 1. Emit cases YAML
        emit_yaml_suite(cases, output_dir)

        # 2. Emit rubrics Markdown
        emit_rubrics(clusters, output_dir, traces=traces)

        # 3. Emit pytest suite (conftest.py + test_generated.py)
        emit_pytest_suite(output_dir)

        return len(cases), len(clusters)
    finally:
        store.close()
