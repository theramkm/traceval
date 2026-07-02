# ruff: noqa: E501
from collections import Counter
from pathlib import Path

from traceval.analyze.cluster import Cluster
from traceval.model import Trace

RUBRIC_TEMPLATE = """# Rubric: {cluster_name}

This rubric is used by the LLM-as-a-judge to evaluate agent outputs for this cluster.
Please review and customize the guidelines below (resolve all TODO markers).

## Evaluation Criteria
- TODO(review): Verify that the agent correctly addresses the request. Focus terms: {top_terms}.
- TODO(review): Ensure the assistant response tone is helpful, concise, and professional.
- TODO(review): Check that the agent correctly invokes tools (e.g. {tool_signature}) as expected.{failure_criteria}

## Scoring Instructions
Return a JSON object in this exact format:
```json
{{
  "score": <float between 0.0 and 1.0>,
  "reasons": ["list of reasons or feedback strings"]
}}
```
"""


def _dominant_failure_label(
    cluster: Cluster,
    traces_by_id: dict[str, Trace],
) -> str | None:
    labels = [
        traces_by_id[tid].outcome.label  # type: ignore[union-attr]
        for tid in cluster.trace_ids
        if tid in traces_by_id and traces_by_id[tid].outcome
    ]
    if not labels:
        return None
    dominant = Counter(labels).most_common(1)[0][0]
    return dominant if dominant != "success" else None


def emit_rubrics(
    clusters: list[Cluster],
    output_dir: Path,
    traces: list[Trace] | None = None,
) -> None:
    rubrics_dir = output_dir / "rubrics"
    rubrics_dir.mkdir(parents=True, exist_ok=True)

    traces_by_id = {t.trace_id: t for t in traces} if traces else {}

    for cluster in clusters:
        name = cluster.name
        top_terms = (
            ", ".join(cluster.top_terms) if cluster.top_terms else "general requests"
        )
        sig = (
            cluster.tool_signature.replace(">", " -> ")
            if cluster.tool_signature
            else "no tools used"
        )

        failure_criteria = ""
        failure_label = _dominant_failure_label(cluster, traces_by_id)
        if failure_label:
            failure_criteria = (
                f"\n- The agent must NOT exhibit failure mode: {failure_label}."
            )

        content = RUBRIC_TEMPLATE.format(
            cluster_name=name,
            top_terms=top_terms,
            tool_signature=sig,
            failure_criteria=failure_criteria,
        )

        rubric_file = rubrics_dir / f"{cluster.id}.md"
        rubric_file.write_text(content, encoding="utf-8")
