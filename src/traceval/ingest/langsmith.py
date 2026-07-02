import json
import logging
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from pydantic import ValidationError

from traceval.ingest.base import Adapter
from traceval.model import LLMCall, Message, Step, ToolCall, Trace

logger = logging.getLogger("traceval.ingest")


def parse_iso_datetime(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return None


class LangsmithAdapter(Adapter):
    format_name: ClassVar[str] = "langsmith"

    def __init__(self, tool_span_globs: list[str] | None = None) -> None:
        # LangSmith runs carry an explicit run_type; globs are unused.
        self.tool_span_globs = tool_span_globs

    def detect(self, first_lines: list[str]) -> bool:
        if not first_lines:
            return False
        try:
            data = json.loads(first_lines[0])
            return "run_type" in data and "parent_run_id" in data and "inputs" in data
        except Exception:
            return False

    def parse(self, path: Path) -> Iterator[Trace]:
        runs_by_trace: dict[str, list[dict[str, Any]]] = {}

        # 1. Read all runs from file
        with open(path, encoding="utf-8") as f:
            for line_idx, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    run_data = json.loads(line)
                    trace_id = run_data.get("trace_id")
                    if not trace_id:
                        # Fallback: if parent_run_id is null, id can be the trace_id
                        if not run_data.get("parent_run_id"):
                            trace_id = run_data.get("id")
                        else:
                            trace_id = "unknown"
                    runs_by_trace.setdefault(trace_id, []).append(run_data)
                except Exception as e:
                    logger.warning(
                        "Line %d: failed to parse LangSmith run. Error: %s",
                        line_idx,
                        str(e),
                    )

        # 2. Reconstruct traces from runs
        for trace_id, runs in runs_by_trace.items():
            if trace_id == "unknown":
                continue
            try:
                # Find root run
                root_run = next((r for r in runs if not r.get("parent_run_id")), None)
                if not root_run:
                    root_run = runs[0]

                started_at = (
                    parse_iso_datetime(root_run.get("start_time")) or datetime.utcnow()
                )
                ended_at = parse_iso_datetime(root_run.get("end_time"))

                inputs = root_run.get("inputs") or {}
                outputs = root_run.get("outputs") or {}

                task_input = ""
                if "input" in inputs:
                    task_input = str(inputs["input"])
                elif inputs:
                    # Fallback: stringify first value
                    task_input = str(next(iter(inputs.values())))

                final_output = None
                if outputs:
                    if "output" in outputs:
                        final_output = str(outputs["output"])
                    else:
                        final_output = str(next(iter(outputs.values())))

                child_runs = [r for r in runs if r is not root_run]
                # Reconstruct order chronologically
                child_runs.sort(key=lambda r: r.get("start_time") or "")

                steps = []
                for idx, run in enumerate(child_runs):
                    run_type = run.get("run_type")
                    name = run.get("name", "")
                    run_id = run.get("id", f"run-{idx}")

                    start_t = parse_iso_datetime(run.get("start_time"))
                    end_t = parse_iso_datetime(run.get("end_time"))
                    latency_ms = None
                    if start_t and end_t:
                        latency_ms = (end_t - start_t).total_seconds() * 1000.0

                    error_msg = run.get("error")
                    run_inputs = run.get("inputs") or {}
                    run_outputs = run.get("outputs") or {}
                    extra = run.get("extra") or {}

                    if run_type == "llm":
                        # Input messages
                        input_messages = []
                        messages_val = run_inputs.get("messages")
                        if isinstance(messages_val, list):
                            for m in messages_val:
                                if isinstance(m, dict):
                                    input_messages.append(
                                        Message(
                                            role=m.get("role", "user"),
                                            content=str(m.get("content", "")),
                                            tool_call_id=m.get("tool_call_id"),
                                        )
                                    )
                                else:
                                    input_messages.append(
                                        Message(role="user", content=str(m))
                                    )
                        elif messages_val is not None:
                            input_messages.append(
                                Message(role="user", content=str(messages_val))
                            )

                        # Output message
                        output_msg = None
                        gens = run_outputs.get("generations")
                        if isinstance(gens, list) and gens:
                            first_gen = gens[0]
                            if isinstance(first_gen, dict):
                                message_val = first_gen.get("message")
                                if isinstance(message_val, dict):
                                    output_msg = Message(
                                        role=message_val.get("role", "assistant"),
                                        content=str(message_val.get("content", "")),
                                    )
                                elif "text" in first_gen:
                                    output_msg = Message(
                                        role="assistant",
                                        content=str(first_gen["text"]),
                                    )

                        token_usage = extra.get("token_usage") or {}
                        prompt_tokens = token_usage.get("prompt_tokens")
                        comp_tokens = token_usage.get("completion_tokens")
                        model_name = extra.get("metadata", {}).get("ls_model_name")

                        llm_call = LLMCall(
                            span_id=run_id,
                            model=model_name,
                            input_messages=input_messages,
                            output_message=output_msg,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=comp_tokens,
                            latency_ms=latency_ms,
                            error=error_msg,
                        )
                        steps.append(
                            Step(
                                index=idx,
                                kind="llm",
                                llm=llm_call,
                                raw_attributes={
                                    k: str(v)
                                    for k, v in run.items()
                                    if k not in ["inputs", "outputs"]
                                },
                            )
                        )

                    elif run_type == "tool":
                        arguments_json = json.dumps(run_inputs)
                        tool_output = None
                        if run_outputs:
                            if "output" in run_outputs:
                                tool_output = str(run_outputs["output"])
                            else:
                                tool_output = str(next(iter(run_outputs.values())))

                        tool_call = ToolCall(
                            span_id=run_id,
                            name=name,
                            arguments_json=arguments_json,
                            output=tool_output,
                            error=error_msg,
                            latency_ms=latency_ms,
                        )
                        steps.append(
                            Step(
                                index=idx,
                                kind="tool",
                                tool=tool_call,
                                raw_attributes={
                                    k: str(v)
                                    for k, v in run.items()
                                    if k not in ["inputs", "outputs"]
                                },
                            )
                        )

                    else:
                        steps.append(
                            Step(
                                index=idx,
                                kind="other",
                                raw_attributes={
                                    k: str(v)
                                    for k, v in run.items()
                                    if k not in ["inputs", "outputs"]
                                },
                            )
                        )

                metadata = {
                    k: str(v)
                    for k, v in root_run.get("extra", {}).get("metadata", {}).items()
                }
                for k in ["name", "id"]:
                    if root_run.get(k) is not None:
                        metadata[k] = str(root_run[k])

                yield Trace(
                    trace_id=trace_id,
                    source="langsmith",
                    started_at=started_at,
                    ended_at=ended_at,
                    task_input=task_input,
                    final_output=final_output,
                    steps=steps,
                    metadata=metadata,
                )
            except ValidationError as ve:
                logger.warning(
                    "LangSmith trace %s failed validation. Error: %s",
                    trace_id,
                    str(ve),
                )
            except Exception as ex:
                logger.warning(
                    "LangSmith trace %s failed reconstruction. Error: %s",
                    trace_id,
                    str(ex),
                )
