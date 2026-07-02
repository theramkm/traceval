# ruff: noqa: E501
from pathlib import Path

from traceval.analyze.cluster import Cluster

RUBRIC_TEMPLATE = """# Rubric: {cluster_name}

This rubric is used by the LLM-as-a-judge to evaluate agent outputs for this cluster.
Please review and customize the guidelines below (resolve all TODO markers).

## Evaluation Criteria
- TODO(review): Verify that the agent correctly addresses the request. Focus terms: {top_terms}.
- TODO(review): Ensure the assistant response tone is helpful, concise, and professional.
- TODO(review): Check that the agent correctly invokes tools (e.g. {tool_signature}) as expected.

## Scoring Instructions
Return a JSON object in this exact format:
```json
{{
  "score": <float between 0.0 and 1.0>,
  "reasons": ["list of reasons or feedback strings"]
}}
```
"""


def emit_rubrics(
    clusters: list[Cluster],
    output_dir: Path,
) -> None:
    rubrics_dir = output_dir / "rubrics"
    rubrics_dir.mkdir(parents=True, exist_ok=True)

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

        content = RUBRIC_TEMPLATE.format(
            cluster_name=name,
            top_terms=top_terms,
            tool_signature=sig,
        )

        rubric_file = rubrics_dir / f"{cluster.id}.md"
        rubric_file.write_text(content, encoding="utf-8")
