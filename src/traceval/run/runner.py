import time
from pathlib import Path
from typing import Any

from traceval.run.judge import Judge
from traceval.run.scorers import (
    score_contains_any,
    score_exact,
    score_json_schema,
    score_judge,
    score_no_tool_loop,
    score_not_contains,
    score_regex,
    score_tool_sequence,
)
from traceval.run.target import Target


def run_single_case(
    case: dict[str, Any],
    target: Target,
    judge: Judge,
) -> dict[str, Any]:
    start_time = time.perf_counter()
    try:
        res = target.invoke(case["input"])
        output_text = res.get("output", "")
        actual_tools = res.get("tool_calls", [])
    except Exception as e:
        end_time = time.perf_counter()
        return {
            "passed": False,
            "detail": f"Target invocation failed with exception: {e}",
            "latency_ms": (end_time - start_time) * 1000.0,
            "scores": {},
        }
    end_time = time.perf_counter()
    latency_ms = (end_time - start_time) * 1000.0

    checks = case.get("expected", {}).get("checks", [])
    scores = {}
    passed = True
    failed_details = []

    for check_idx, check in enumerate(checks):
        check_type = check.get("type")
        res_score = None

        if check_type == "exact":
            res_score = score_exact(output_text, check.get("value", ""))
        elif check_type == "contains_any":
            res_score = score_contains_any(output_text, check.get("values", []))
        elif check_type == "not_contains":
            res_score = score_not_contains(output_text, check.get("values", []))
        elif check_type == "no_tool_loop":
            res_score = score_no_tool_loop(
                actual_tools,
                max_repeats=check.get("max_repeats", 3),
            )
        elif check_type == "regex":
            res_score = score_regex(output_text, check.get("pattern", ""))
        elif check_type == "json_schema":
            res_score = score_json_schema(output_text, check.get("schema", {}))
        elif check_type == "tool_sequence":
            res_score = score_tool_sequence(
                actual_tools,
                check.get("tools", []),
                mode=check.get("mode", "order"),
            )
        elif check_type == "judge":
            rubric_path = check.get("rubric")
            rubric_content = ""
            if rubric_path:
                paths_to_try = [
                    Path(rubric_path),
                    Path("evals") / rubric_path,
                    Path(__file__).parent.parent.parent.parent / "evals" / rubric_path,
                    Path(__file__).parent.parent.parent.parent / rubric_path,
                ]

                for p in paths_to_try:
                    if p.exists():
                        try:
                            rubric_content = p.read_text(encoding="utf-8")
                            break
                        except Exception:
                            pass
                else:
                    rubric_content = f"Rubric checklist validation: {rubric_path}"
            else:
                rubric_content = "Evaluate output quality."

            res_score = score_judge(
                judge,
                rubric_content,
                case["input"],
                output_text,
                case.get("reference_output"),
                min_score=check.get("min_score", 0.7),
            )
        else:
            from traceval.run.scorers import ScoreResult

            res_score = ScoreResult(
                passed=True,
                score=1.0,
                detail=f"Skipped unknown check type: {check_type}",
            )

        if res_score:
            key = f"{check_type}_{check_idx}"
            scores[key] = res_score.to_dict()
            if not res_score.passed:
                passed = False
                failed_details.append(f"[{check_type}] {res_score.detail}")

    return {
        "passed": passed,
        "detail": "; ".join(failed_details) if failed_details else "All checks passed",
        "latency_ms": latency_ms,
        "scores": scores,
    }
