import fnmatch
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
        # standard ISO parser
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return None


class OtelAdapter(Adapter):
    format_name: ClassVar[str] = "otel"

    def __init__(self, tool_span_globs: list[str] | None = None) -> None:
        self.tool_span_globs = tool_span_globs

    def detect(self, first_lines: list[str]) -> bool:
        if not first_lines:
            return False
        try:
            data = json.loads(first_lines[0])
            # Check for OTel characteristic keys
            return (
                "trace_id" in data
                and "span_id" in data
                and ("attributes" in data or "parent_span_id" in data)
            )
        except Exception:
            return False

    def parse(self, path: Path) -> Iterator[Trace]:
        spans_by_trace: dict[str, list[dict[str, Any]]] = {}

        # 1. Read all spans from file
        with open(path, encoding="utf-8") as f:
            for line_idx, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    span_data = json.loads(line)
                    trace_id = span_data.get("trace_id")
                    if not trace_id:
                        logger.warning(
                            "Line %d: OTel span missing trace_id.",
                            line_idx,
                        )
                        continue
                    spans_by_trace.setdefault(trace_id, []).append(span_data)
                except Exception as e:
                    logger.warning(
                        "Line %d: failed to parse OTel span. Error: %s",
                        line_idx,
                        str(e),
                    )

        # 2. Reconstruct traces from grouped spans
        for trace_id, spans in spans_by_trace.items():
            try:
                # Find root span (where parent_span_id is null)
                root_span = next(
                    (s for s in spans if not s.get("parent_span_id")), None
                )
                if not root_span:
                    # Fallback to the first span
                    root_span = spans[0]

                started_at = (
                    parse_iso_datetime(root_span.get("start_time")) or datetime.utcnow()
                )
                ended_at = parse_iso_datetime(root_span.get("end_time"))

                attrs = root_span.get("attributes", {})
                task_input = attrs.get("gen_ai.task_input") or ""
                final_output = attrs.get("gen_ai.final_output")

                steps = []
                child_spans = [s for s in spans if s is not root_span]
                # Sort child spans by start_time to keep the
                # steps in chronological order
                child_spans.sort(key=lambda s: s.get("start_time") or "")

                for idx, span in enumerate(child_spans):
                    span_attrs = span.get("attributes", {})
                    name = span.get("name", "")

                    start_t = parse_iso_datetime(span.get("start_time"))
                    end_t = parse_iso_datetime(span.get("end_time"))
                    latency_ms = None
                    if start_t and end_t:
                        latency_ms = (end_t - start_t).total_seconds() * 1000.0

                    # Check if LLM call
                    if (
                        "gen_ai.system" in span_attrs
                        or "gen_ai.prompt" in span_attrs
                        or "gen_ai.completion" in span_attrs
                    ):
                        prompt_val = span_attrs.get("gen_ai.prompt")
                        input_messages = []
                        if prompt_val:
                            try:
                                # Attempt to parse JSON messages array
                                msg_list = json.loads(prompt_val)
                                for m in msg_list:
                                    input_messages.append(
                                        Message(
                                            role=m.get("role", "user"),
                                            content=m.get("content", ""),
                                            tool_call_id=m.get("tool_call_id"),
                                        )
                                    )
                            except Exception:
                                input_messages.append(
                                    Message(role="user", content=str(prompt_val))
                                )

                        output_msg = None
                        comp_val = span_attrs.get("gen_ai.completion")
                        if comp_val:
                            output_msg = Message(role="assistant", content=comp_val)

                        prompt_tokens = None
                        comp_tokens = None
                        if "gen_ai.usage.prompt_tokens" in span_attrs:
                            try:
                                prompt_tokens = int(
                                    span_attrs["gen_ai.usage.prompt_tokens"]
                                )
                            except ValueError:
                                pass
                        if "gen_ai.usage.completion_tokens" in span_attrs:
                            try:
                                comp_tokens = int(
                                    span_attrs["gen_ai.usage.completion_tokens"]
                                )
                            except ValueError:
                                pass

                        llm_call = LLMCall(
                            span_id=span["span_id"],
                            model=span_attrs.get("gen_ai.request.model"),
                            input_messages=input_messages,
                            output_message=output_msg,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=comp_tokens,
                            latency_ms=latency_ms,
                            error=span_attrs.get("gen_ai.error"),
                        )
                        steps.append(
                            Step(
                                index=idx,
                                kind="llm",
                                llm=llm_call,
                                raw_attributes={
                                    k: str(v) for k, v in span_attrs.items()
                                },
                            )
                        )

                    # Check if Tool call. Primary signal: GenAI semantic
                    # convention attributes. Fallbacks are attribute- or
                    # user-glob-based only, never tool-name lists.
                    elif (
                        "gen_ai.tool.name" in span_attrs
                        or "gen_ai.tool.arguments" in span_attrs
                        or span_attrs.get("gen_ai.operation.name") == "execute_tool"
                        or "tool.name" in span_attrs
                        or (
                            self.tool_span_globs is not None
                            and any(
                                fnmatch.fnmatch(name, pattern)
                                for pattern in self.tool_span_globs
                            )
                        )
                    ):
                        tool_name = (
                            span_attrs.get("gen_ai.tool.name")
                            or span_attrs.get("tool.name")
                            or name
                        )
                        args_json = span_attrs.get("gen_ai.tool.arguments") or "{}"
                        tool_call = ToolCall(
                            span_id=span["span_id"],
                            name=tool_name,
                            arguments_json=args_json,
                            output=span_attrs.get("gen_ai.tool.output"),
                            error=span_attrs.get("gen_ai.tool.error")
                            or span_attrs.get("gen_ai.error"),
                            latency_ms=latency_ms,
                        )
                        steps.append(
                            Step(
                                index=idx,
                                kind="tool",
                                tool=tool_call,
                                raw_attributes={
                                    k: str(v) for k, v in span_attrs.items()
                                },
                            )
                        )

                    else:
                        steps.append(
                            Step(
                                index=idx,
                                kind="other",
                                raw_attributes={
                                    k: str(v) for k, v in span_attrs.items()
                                },
                            )
                        )

                yield Trace(
                    trace_id=trace_id,
                    source="otel",
                    started_at=started_at,
                    ended_at=ended_at,
                    task_input=task_input,
                    final_output=final_output,
                    steps=steps,
                    metadata={
                        k: str(v)
                        for k, v in attrs.items()
                        if not k.startswith("gen_ai.task_input")
                        and not k.startswith("gen_ai.final_output")
                    },
                )
            except ValidationError as ve:
                logger.warning(
                    "OTel trace %s failed validation. Error: %s",
                    trace_id,
                    str(ve),
                )
            except Exception as ex:
                logger.warning(
                    "OTel trace %s failed reconstruction. Error: %s",
                    trace_id,
                    str(ex),
                )
