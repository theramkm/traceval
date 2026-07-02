# ruff: noqa: E501
import json
import re
from typing import Any

import jsonschema

from traceval.run.judge import Judge


class ScoreResult:
    def __init__(self, passed: bool, score: float, detail: str) -> None:
        self.passed = passed
        self.score = score
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "detail": self.detail,
        }


def score_exact(output: str, expected_str: str) -> ScoreResult:
    passed = output.strip() == expected_str.strip()
    return ScoreResult(
        passed=passed,
        score=1.0 if passed else 0.0,
        detail="Exact match passed" if passed else "Exact match failed",
    )


def score_contains_any(output: str, values: list[str]) -> ScoreResult:
    matched = []
    output_lower = output.lower()
    for val in values:
        if val.lower() in output_lower:
            matched.append(val)
    passed = len(matched) > 0
    return ScoreResult(
        passed=passed,
        score=1.0 if passed else 0.0,
        detail=(
            f"Matched containing values: {matched}"
            if passed
            else f"Failed to match any of values: {values}"
        ),
    )


def score_not_contains(output: str, values: list[str]) -> ScoreResult:
    matched = []
    output_lower = output.lower()
    for val in values:
        if val.lower() in output_lower:
            matched.append(val)
    passed = len(matched) == 0
    return ScoreResult(
        passed=passed,
        score=1.0 if passed else 0.0,
        detail=(
            f"No forbidden values present: {values}"
            if passed
            else f"Forbidden values found in output: {matched}"
        ),
    )


def score_regex(output: str, pattern: str) -> ScoreResult:
    match = re.search(pattern, output, re.IGNORECASE)
    passed = match is not None
    return ScoreResult(
        passed=passed,
        score=1.0 if passed else 0.0,
        detail=(
            f"Regex pattern '{pattern}' matched"
            if passed
            else f"Regex pattern '{pattern}' not matched"
        ),
    )


def score_json_schema(output: str, schema: dict[str, Any]) -> ScoreResult:
    try:
        data = json.loads(output)
        jsonschema.validate(instance=data, schema=schema)
        return ScoreResult(
            passed=True,
            score=1.0,
            detail="JSON output matches schema validation",
        )
    except json.JSONDecodeError:
        return ScoreResult(
            passed=False,
            score=0.0,
            detail="Failed to parse output string as JSON",
        )
    except jsonschema.ValidationError as ve:
        return ScoreResult(
            passed=False,
            score=0.0,
            detail=f"JSON schema validation failed: {ve.message}",
        )


def score_tool_sequence(
    actual_tools: list[str],
    expected_tools: list[str],
    mode: str = "order",
) -> ScoreResult:
    if mode == "subset":
        # Check that all expected tools are in actual tools
        missing = [t for t in expected_tools if t not in actual_tools]
        passed = len(missing) == 0
        return ScoreResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            detail=(
                "All expected tools executed"
                if passed
                else f"Missing expected tool calls: {missing}"
            ),
        )

    else:
        # Default 'order' mode: check relative order (subsequence check)
        actual_idx = 0
        expected_idx = 0
        while actual_idx < len(actual_tools) and expected_idx < len(expected_tools):
            if actual_tools[actual_idx] == expected_tools[expected_idx]:
                expected_idx += 1
            actual_idx += 1

        passed = expected_idx == len(expected_tools)
        return ScoreResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            detail=(
                "Tools executed in correct sequence order"
                if passed
                else f"Tools sequence mismatch. Expected {expected_tools}, got {actual_tools}"
            ),
        )


def score_no_tool_loop(actual_tools: list[str], max_repeats: int = 3) -> ScoreResult:
    # The runner only sees tool names (targets return flattened tool_calls), so
    # "identical call" degrades to "same name called consecutively" -- a looser
    # variant of the R_LOOP labeler rule in traceval.analyze.outcomes.
    longest_run = 0
    longest_tool = None
    prev = None
    run_len = 0
    for name in actual_tools:
        run_len = run_len + 1 if name == prev else 1
        prev = name
        if run_len > longest_run:
            longest_run = run_len
            longest_tool = name
    passed = longest_run < max_repeats
    return ScoreResult(
        passed=passed,
        score=1.0 if passed else 0.0,
        detail=(
            f"No tool called {max_repeats}+ times consecutively"
            if passed
            else (
                f"Tool loop detected: '{longest_tool}' called "
                f"{longest_run} times consecutively (limit {max_repeats})"
            )
        ),
    )


def score_judge(
    judge: Judge,
    rubric: str,
    input_text: str,
    output_text: str,
    reference: str | None,
    min_score: float = 0.7,
) -> ScoreResult:
    try:
        res = judge.score(rubric, input_text, output_text, reference)
        passed = res.score >= min_score
        return ScoreResult(
            passed=passed,
            score=res.score,
            detail="; ".join(res.reasons),
        )
    except Exception as e:
        return ScoreResult(
            passed=False,
            score=0.0,
            detail=f"Judge evaluation failed with exception: {e}",
        )
