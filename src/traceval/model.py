from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None


class LLMCall(BaseModel):
    span_id: str
    model: str | None = None
    input_messages: list[Message]
    output_message: Message | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float | None = None
    error: str | None = None


class ToolCall(BaseModel):
    span_id: str
    name: str
    arguments_json: str  # raw json string, never parsed-and-lost
    output: str | None = None
    error: str | None = None
    latency_ms: float | None = None


class Step(BaseModel):
    index: int
    kind: Literal["llm", "tool", "retrieval", "other"]
    llm: LLMCall | None = None
    tool: ToolCall | None = None
    raw_attributes: dict[str, str] = {}  # lossless escape hatch


class Outcome(BaseModel):
    label: Literal[
        "success",
        "tool_error",
        "validation_error",
        "loop",
        "timeout",
        "bad_output",
        "unknown",
    ]
    reason: str  # human-readable, always populated
    labeled_by: Literal["rule", "user_rule", "manual"]
    rule_id: str | None = None


class Trace(BaseModel):
    schema_version: str = "1"
    trace_id: str
    source: str  # "otel" | "langfuse" | "langsmith" | "generic"
    started_at: datetime
    ended_at: datetime | None = None
    task_input: str  # the user-facing request that started the trace
    final_output: str | None = None
    steps: list[Step]
    metadata: dict[str, str] = {}
    outcome: Outcome | None = None  # filled by analyze
