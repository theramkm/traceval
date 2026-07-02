import importlib
import json
import re
from collections.abc import Callable
from typing import Any

from traceval.analyze.cluster import (
    Cluster,
    get_ngrams,
    normalize_numeric_tokens,
    tokenize,
)
from traceval.model import Trace

# Standard regexes for PII
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"\+?\d{1,4}[-.\s]?\(?\d{1,3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
CARD_REGEX = re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b")
TOKEN_REGEX = re.compile(
    r"(?:bearer\s+[a-zA-Z0-9_\-\.\~+\/]+=*|sk-[a-zA-Z0-9]{20,})",
    re.IGNORECASE,
)


def redact_text(
    text: str,
    custom_hook: Callable[[str], str] | None = None,
) -> str:
    if not text:
        return text

    text = TOKEN_REGEX.sub("[REDACTED_TOKEN]", text)
    text = CARD_REGEX.sub("[REDACTED_CARD]", text)
    text = EMAIL_REGEX.sub("[REDACTED_EMAIL]", text)
    text = PHONE_REGEX.sub("[REDACTED_PHONE]", text)

    # Apply custom hook if provided
    if custom_hook:
        try:
            text = custom_hook(text)
        except Exception:
            pass

    return text


def load_redact_hook(hook_str: str) -> Callable[[str], str]:
    parts = hook_str.split(":")
    if len(parts) != 2:
        raise ValueError("Redact hook must be in format module:function")
    mod_name, func_name = parts
    # Ensure module is importable from cwd
    import os
    import sys

    sys.path.insert(0, os.getcwd())
    mod = importlib.import_module(mod_name)
    import typing

    func = getattr(mod, func_name)
    return typing.cast(Callable[[str], str], func)


def _judge_check(cluster_id: str) -> dict[str, Any]:
    return {
        "type": "judge",
        "rubric": f"rubrics/{cluster_id}.md",
        "min_score": 0.7,
    }


def _build_golden_checks(trace: Trace, cluster_id: str) -> list[dict[str, Any]]:
    """Positive checks copied from a successful trace's recorded behavior."""
    tools_used = [
        step.tool.name for step in trace.steps if step.kind == "tool" and step.tool
    ]

    # Build json_schema check if final output parses as json
    final_out = trace.final_output or ""
    is_json = False
    try:
        if final_out.strip().startswith(("{", "[")):
            json.loads(final_out)
            is_json = True
    except Exception:
        pass

    # Inferred simple contains checks from high TF-IDF terms or words
    contains_values = []
    if trace.final_output:
        words = tokenize(trace.final_output)
        # Pick up to 2 representative terms
        contains_values = words[:2]

    checks: list[dict[str, Any]] = []
    if is_json:
        checks.append(
            {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            }
        )
    if contains_values:
        checks.append(
            {
                "type": "contains_any",
                "values": contains_values,
            }
        )
    if tools_used:
        checks.append(
            {
                "type": "tool_sequence",
                "tools": tools_used,
            }
        )

    checks.append(_judge_check(cluster_id))
    return checks


def _error_signature_tokens(final_output: str, task_input: str) -> list[str]:
    """Tokens characteristic of a failure output, for not_contains checks.

    Tokens that also appear in the task input are excluded (a healthy answer
    naturally echoes the question), as are short generic words.
    """
    input_tokens = set(tokenize(task_input))
    signature: list[str] = []
    for token in tokenize(final_output):
        if len(token) < 4 or token in input_tokens or token in signature:
            continue
        signature.append(token)
        if len(signature) == 4:
            break
    return signature


def _build_regression_checks(trace: Trace, cluster_id: str) -> list[dict[str, Any]]:
    """Inverted checks: the agent must NOT reproduce the recorded failure.

    Nothing from a failure trace is asserted as a positive expectation --
    regression cases mean "the agent must now not fail this way", so the
    failure's output tokens become forbidden and its loop becomes a bound.
    """
    checks: list[dict[str, Any]] = []
    label = trace.outcome.label if trace.outcome else "unknown"
    final_out = trace.final_output or ""

    if final_out.strip():
        signature = _error_signature_tokens(final_out, trace.task_input)
        if signature:
            checks.append({"type": "not_contains", "values": signature})
    else:
        # The failure produced no output (e.g. timeout); require any output.
        checks.append({"type": "regex", "pattern": r"\S"})

    if label == "loop":
        checks.append({"type": "no_tool_loop", "max_repeats": 3})

    checks.append(_judge_check(cluster_id))
    return checks


def select_and_redact_cases(
    clusters: list[Cluster],
    traces: list[Trace],
    per_cluster: int = 3,
    include_failures: bool = False,
    redact_hook_str: str | None = None,
) -> list[dict[str, Any]]:
    # Load custom redact hook if provided
    custom_hook = None
    if redact_hook_str:
        custom_hook = load_redact_hook(redact_hook_str)

    traces_by_id = {t.trace_id: t for t in traces}
    selected_cases: list[dict[str, Any]] = []

    for cluster in clusters:
        cluster_traces = [
            traces_by_id[tid] for tid in cluster.trace_ids if tid in traces_by_id
        ]

        # Deduplicate traces in the cluster (near-identical task_input Jaccard >= 0.85)
        unique_traces: list[Trace] = []
        for t in cluster_traces:
            t_ngrams = get_ngrams(normalize_numeric_tokens(tokenize(t.task_input)))
            is_dup = False
            for ut in unique_traces:
                ut_ngrams = get_ngrams(
                    normalize_numeric_tokens(tokenize(ut.task_input))
                )
                if not t_ngrams or not ut_ngrams:
                    sim = 0.0
                else:
                    union_len = len(t_ngrams.union(ut_ngrams))
                    sim = (
                        len(t_ngrams.intersection(ut_ngrams)) / union_len
                        if union_len > 0
                        else 0.0
                    )
                if sim >= 0.85:
                    is_dup = True
                    break
            if not is_dup:
                unique_traces.append(t)

        # Separate into golden (success) and regression (failures)
        goldens = [
            t for t in unique_traces if t.outcome and t.outcome.label == "success"
        ]
        failures = [
            t for t in unique_traces if t.outcome and t.outcome.label != "success"
        ]

        # Prioritize success case first, then failures if allowed,
        # up to per_cluster total cases
        cases_to_generate: list[tuple[Trace, str]] = []
        if goldens:
            cases_to_generate.append((goldens[0], "golden"))

        if include_failures:
            for f in failures:
                if len(cases_to_generate) < per_cluster:
                    cases_to_generate.append((f, "regression"))

        # Fallback to other successes if space left
        if len(cases_to_generate) < per_cluster:
            for g in goldens[1:]:
                if len(cases_to_generate) < per_cluster:
                    cases_to_generate.append((g, "golden"))

        for trace, kind in cases_to_generate:
            if kind == "regression":
                checks = _build_regression_checks(trace, cluster.id)
                # The failure output must not reach the judge as a golden
                # reference; keep it in notes for human reviewers instead.
                reference_output = ""
                label = trace.outcome.label if trace.outcome else "unknown"
                failure_output = redact_text(trace.final_output or "", custom_hook)
                notes = (
                    f"AUTO-GENERATED regression case from failed trace "
                    f"{trace.trace_id} (label={label}): the agent must NOT "
                    f"fail this way again. Source failure output: "
                    f"{failure_output!r}. Review checks before trusting."
                )
            else:
                checks = _build_golden_checks(trace, cluster.id)
                reference_output = redact_text(trace.final_output or "", custom_hook)
                notes = (
                    f"AUTO-GENERATED from trace {trace.trace_id}. "
                    f"Review checks before trusting."
                )

            # Build case object
            case_data = {
                "schema_version": "1",
                "id": f"{cluster.id}__case_{len(selected_cases) + 1:03d}",
                "source_trace_id": trace.trace_id,
                "cluster": cluster.id,
                "kind": kind,
                "input": redact_text(trace.task_input, custom_hook),
                "expected": {"checks": checks},
                "reference_output": reference_output,
                "notes": notes,
            }
            selected_cases.append(case_data)

    return selected_cases
