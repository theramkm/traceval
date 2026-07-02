from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = """schema_version: "1"
target:
  default_url: "http://localhost:8000/agent"
  timeout_s: 30
judge:
  default_provider: "fake"
  max_judge_calls: 200
"""


def emit_yaml_suite(
    cases: list[dict[str, Any]],
    output_dir: Path,
) -> None:
    # 1. Ensure output directories exist
    output_dir.mkdir(parents=True, exist_ok=True)
    cases_dir = output_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    # 2. Write each case
    for case in cases:
        cluster_id = case["cluster"]
        cluster_dir = cases_dir / cluster_id
        cluster_dir.mkdir(parents=True, exist_ok=True)

        case_file = cluster_dir / f"{case['id']}.yaml"
        # Write clean, human-readable YAML
        with open(case_file, "w", encoding="utf-8") as f:
            # We add a nice review banner comment at the top
            f.write("# AUTO-GENERATED, review me before trusting in CI\n")
            yaml.safe_dump(
                case,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

    # 3. Write traceval.yaml configuration default
    config_file = output_dir / "traceval.yaml"
    if not config_file.exists():
        config_file.write_text(DEFAULT_CONFIG, encoding="utf-8")
