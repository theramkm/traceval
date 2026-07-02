import importlib.util
import logging
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from traceval.model import Outcome, Trace


class Rule:
    def __init__(
        self,
        rule_id: str,
        description: str,
        fn: Callable[[Trace], Outcome | None],
    ) -> None:
        self.rule_id = rule_id
        self.description = description
        self.fn = fn


def R_TOOL_ERROR(trace: Trace) -> Outcome | None:
    for step in trace.steps:
        if step.kind == "tool" and step.tool and step.tool.error:
            return Outcome(
                label="tool_error",
                reason=f"Tool '{step.tool.name}' failed with error: {step.tool.error}",
                labeled_by="rule",
                rule_id="R_TOOL_ERROR",
            )
    return None


def R_LLM_ERROR(trace: Trace) -> Outcome | None:
    for step in trace.steps:
        if step.kind == "llm" and step.llm and step.llm.error:
            return Outcome(
                label="bad_output",
                reason=(
                    f"LLM call in step {step.index} failed with error: {step.llm.error}"
                ),
                labeled_by="rule",
                rule_id="R_LLM_ERROR",
            )
    return None


def R_LOOP(trace: Trace, loop_step_threshold: int = 25) -> Outcome | None:
    # 1. Check total steps
    if len(trace.steps) > loop_step_threshold:
        return Outcome(
            label="loop",
            reason=(
                f"Total steps ({len(trace.steps)}) exceeded loop step "
                f"threshold ({loop_step_threshold})"
            ),
            labeled_by="rule",
            rule_id="R_LOOP",
        )

    # 2. Check identical consecutive tool calls (>=3 times)
    consec_count = 0
    last_name = None
    last_args = None

    for step in trace.steps:
        if step.kind == "tool" and step.tool:
            curr_name = step.tool.name
            curr_args = step.tool.arguments_json
            if curr_name == last_name and curr_args == last_args:
                consec_count += 1
                if consec_count >= 3:
                    return Outcome(
                        label="loop",
                        reason=(
                            f"Tool '{curr_name}' called with identical "
                            f"arguments {consec_count} times consecutively"
                        ),
                        labeled_by="rule",
                        rule_id="R_LOOP",
                    )
            else:
                consec_count = 1
                last_name = curr_name
                last_args = curr_args
        else:
            # reset consecutive count if another step kind occurs
            consec_count = 0
            last_name = None
            last_args = None

    return None


def R_TIMEOUT(trace: Trace, timeout_s: float = 300.0) -> Outcome | None:
    if not trace.ended_at:
        return Outcome(
            label="timeout",
            reason="Trace has not completed (ended_at is missing)",
            labeled_by="rule",
            rule_id="R_TIMEOUT",
        )

    duration = (trace.ended_at - trace.started_at).total_seconds()
    if duration > timeout_s:
        return Outcome(
            label="timeout",
            reason=f"Trace duration ({duration:.1f}s) exceeded limit of {timeout_s}s",
            labeled_by="rule",
            rule_id="R_TIMEOUT",
        )
    return None


DEFAULT_VALIDATION_REGEXES = [
    re.compile(r"validation\s+error", re.IGNORECASE),
    re.compile(r"field\s+required", re.IGNORECASE),
    re.compile(r"value\s+is\s+not\s+a\s+valid", re.IGNORECASE),
    re.compile(r"json-schema", re.IGNORECASE),
    re.compile(r"json\s+schema\s+error", re.IGNORECASE),
]


def R_VALIDATION(trace: Trace) -> Outcome | None:
    if not trace.final_output:
        return None
    for pattern in DEFAULT_VALIDATION_REGEXES:
        if pattern.search(trace.final_output):
            return Outcome(
                label="validation_error",
                reason=(
                    f"Final output matched validation signature pattern: "
                    f"'{pattern.pattern}'"
                ),
                labeled_by="rule",
                rule_id="R_VALIDATION",
            )
    return None


def R_EMPTY_OUTPUT(trace: Trace) -> Outcome | None:
    if trace.task_input and not trace.final_output:
        return Outcome(
            label="bad_output",
            reason="Task input is non-empty, but final output is empty or missing",
            labeled_by="rule",
            rule_id="R_EMPTY_OUTPUT",
        )
    return None


def R_DEFAULT_SUCCESS(trace: Trace) -> Outcome | None:
    if trace.final_output:
        return Outcome(
            label="success",
            reason="Trace completed with non-empty final output",
            labeled_by="rule",
            rule_id="R_DEFAULT_SUCCESS",
        )
    return None


def R_UNKNOWN(trace: Trace) -> Outcome | None:
    return Outcome(
        label="unknown",
        reason="No rules matched this trace",
        labeled_by="rule",
        rule_id="R_UNKNOWN",
    )


BUILTIN_RULES = [
    R_TOOL_ERROR,
    R_LLM_ERROR,
    R_LOOP,
    R_TIMEOUT,
    R_VALIDATION,
    R_EMPTY_OUTPUT,
    R_DEFAULT_SUCCESS,
    R_UNKNOWN,
]


def load_user_rules(rules_path: str | Path) -> list[Any]:
    path = Path(rules_path)
    if not path.exists():
        raise FileNotFoundError(f"Custom rules file not found: {rules_path}")

    spec = importlib.util.spec_from_file_location("custom_rules", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load custom rules from {rules_path}")

    mod = importlib.util.module_from_spec(spec)
    sys.modules["custom_rules"] = mod
    spec.loader.exec_module(mod)

    rules = getattr(mod, "RULES", [])
    return rules


def label_trace(
    trace: Trace,
    user_rules: list[Any] | None = None,
    loop_step_threshold: int = 25,
    timeout_s: float = 300.0,
) -> Outcome:
    # 1. Run user rules first
    if user_rules:
        for rule in user_rules:
            # support both Rule objects and simple callables
            fn = getattr(rule, "fn", rule)
            rule_id = getattr(rule, "rule_id", getattr(fn, "__name__", "user_rule"))
            try:
                res = fn(trace)
                if res is not None:
                    # ensure correct metadata is set for user rule label
                    if isinstance(res, Outcome):
                        return Outcome(
                            label=res.label,
                            reason=res.reason,
                            labeled_by="user_rule",
                            rule_id=res.rule_id or rule_id,
                        )
                    return Outcome(
                        label=res,
                        reason=f"Matched custom rule '{rule_id}'",
                        labeled_by="user_rule",
                        rule_id=rule_id,
                    )
            except Exception as e:
                logger = logging.getLogger("traceval.analyze")
                logger.error("Error executing user rule '%s': %s", rule_id, str(e))

    # 2. Run built-in rules
    # loop and timeout require extra arguments
    for rule_fn in BUILTIN_RULES:
        if rule_fn is R_LOOP:
            res = R_LOOP(trace, loop_step_threshold=loop_step_threshold)
        elif rule_fn is R_TIMEOUT:
            res = R_TIMEOUT(trace, timeout_s=timeout_s)
        else:
            res = rule_fn(trace)

        if res is not None:
            return res

    return Outcome(
        label="unknown",
        reason="Default fallback",
        labeled_by="rule",
        rule_id="R_UNKNOWN",
    )
