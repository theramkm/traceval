import json
import logging
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import ClassVar

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


class LangfuseAdapter(Adapter):
    format_name: ClassVar[str] = "langfuse"

    def detect(self, first_lines: list[str]) -> bool:
        if not first_lines:
            return False
        try:
            data = json.loads(first_lines[0])
            return "observations" in data and "timestamp" in data and "id" in data
        except Exception:
            return False

    def parse(self, path: Path) -> Iterator[Trace]:
        with open(path, encoding="utf-8") as f:
            for line_idx, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    trace_id = data.get("id")
                    if not trace_id:
                        logger.warning(
                            "Line %d: Langfuse trace missing id.",
                            line_idx,
                        )
                        continue

                    started_at = (
                        parse_iso_datetime(data.get("timestamp")) or datetime.utcnow()
                    )
                    task_input = str(data.get("input") or "")
                    final_output = None
                    if data.get("output") is not None:
                        final_output = str(data.get("output"))

                    observations = data.get("observations", [])
                    # Sort observations chronologically
                    observations.sort(key=lambda o: o.get("startTime") or "")

                    steps = []
                    for idx, obs in enumerate(observations):
                        obs_type = obs.get("type")
                        name = obs.get("name", "")
                        span_id = obs.get("id", f"obs-{idx}")

                        start_t = parse_iso_datetime(obs.get("startTime"))
                        end_t = parse_iso_datetime(obs.get("endTime"))
                        latency_ms = None
                        if start_t and end_t:
                            latency_ms = (end_t - start_t).total_seconds() * 1000.0

                        level = obs.get("level")
                        error_msg = (
                            obs.get("statusMessage") if level == "ERROR" else None
                        )

                        if obs_type == "GENERATION":
                            obs_input = obs.get("input")
                            input_messages = []
                            if isinstance(obs_input, list):
                                for m in obs_input:
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
                            elif obs_input is not None:
                                input_messages.append(
                                    Message(role="user", content=str(obs_input))
                                )

                            obs_output = obs.get("output")
                            output_msg = None
                            if isinstance(obs_output, dict):
                                output_msg = Message(
                                    role=obs_output.get("role", "assistant"),
                                    content=str(obs_output.get("content", "")),
                                )
                            elif obs_output is not None:
                                output_msg = Message(
                                    role="assistant",
                                    content=str(obs_output),
                                )

                            usage = obs.get("usage") or {}
                            prompt_tokens = usage.get("promptTokens")
                            comp_tokens = usage.get("completionTokens")

                            llm_call = LLMCall(
                                span_id=span_id,
                                model=obs.get("model"),
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
                                        for k, v in obs.items()
                                        if k not in ["input", "output", "observations"]
                                    },
                                )
                            )

                        elif obs_type == "SPAN":
                            # Check if tool span
                            is_tool = (
                                name in ["order_lookup", "stripe_lookup", "kb_search"]
                                or obs.get("metadata", {}).get("tool") is not None
                            )
                            if is_tool:
                                obs_input = obs.get("input")
                                if isinstance(obs_input, (dict, list)):
                                    arguments_json = json.dumps(obs_input)
                                else:
                                    arguments_json = (
                                        str(obs_input)
                                        if obs_input is not None
                                        else "{}"
                                    )

                                obs_output = obs.get("output")
                                tool_output = (
                                    str(obs_output) if obs_output is not None else None
                                )

                                tool_call = ToolCall(
                                    span_id=span_id,
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
                                            for k, v in obs.items()
                                            if k
                                            not in ["input", "output", "observations"]
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
                                            for k, v in obs.items()
                                            if k
                                            not in ["input", "output", "observations"]
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
                                        for k, v in obs.items()
                                        if k not in ["input", "output", "observations"]
                                    },
                                )
                            )

                    metadata = {k: str(v) for k, v in data.get("metadata", {}).items()}
                    # Also include any trace-level properties
                    for k in ["name", "environment"]:
                        if data.get(k) is not None:
                            metadata[k] = str(data[k])

                    yield Trace(
                        trace_id=trace_id,
                        source="langfuse",
                        started_at=started_at,
                        ended_at=None,  # Or calculate max endTime of observations
                        task_input=task_input,
                        final_output=final_output,
                        steps=steps,
                        metadata=metadata,
                    )
                except ValidationError as ve:
                    logger.warning(
                        "Line %d: Langfuse trace %s validation error: %s",
                        line_idx,
                        data.get("id"),
                        str(ve),
                    )
                except Exception as e:
                    logger.warning(
                        "Line %d: failed to parse Langfuse trace. Error: %s",
                        line_idx,
                        str(e),
                    )
