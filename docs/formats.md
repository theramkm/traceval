# Trace Ingestion Formats & Mappings

This document describes how raw trace records from different observability backends are mapped onto the `traceval` canonical `Trace` Pydantic model.

## Canonical Trace Model

All trace adapters transform incoming logs into the `Trace` schema (`src/traceval/model.py`), which includes:
- `trace_id` (str)
- `source` (str: "otel", "langfuse", "langsmith", "generic")
- `started_at` (datetime)
- `ended_at` (datetime or None)
- `task_input` (str, user prompt triggering the trace)
- `final_output` (str or None, assistant's final response)
- `steps` (list of Step objects chronologically ordered):
  - `index` (int)
  - `kind` ("llm", "tool", "retrieval", "other")
  - `llm` (LLMCall or None)
  - `tool` (ToolCall or None)
  - `raw_attributes` (dict[str, str], lossless metadata escape hatch)

---

## 1. Generic format (`generic`)

A line-by-line JSONL file where each line is a raw JSON string validating directly against our canonical `Trace` model. This is the format to convert to when your backend is not natively supported; the two examples below are complete and ingest as-is.

### Required vs optional fields

| Field | Required | Notes |
| --- | --- | --- |
| `trace_id` | yes | Unique string. |
| `source` | yes | Free-form origin label, e.g. `"generic"`. |
| `started_at` | yes | ISO 8601 datetime. |
| `task_input` | yes | The user request that started the trace. |
| `steps` | yes | May be `[]`. Each step needs `index` and `kind` (`llm`, `tool`, `retrieval`, `other`); `llm` steps need an `llm` object with `span_id` and `input_messages`, `tool` steps need a `tool` object with `span_id`, `name`, `arguments_json`. |
| `ended_at` | no | Missing/`null` triggers the built-in timeout rule. |
| `final_output` | no | `null`/empty triggers the empty-output rule. |
| `metadata` | no | `dict[str, str]`. |
| `schema_version`, `outcome` | no | `outcome` is filled by `traceval analyze`; supply it only to pre-label. |

### Example: success trace (one llm step, one tool step)

```json
{"trace_id": "tr-ok-1", "source": "generic", "started_at": "2026-07-01T12:00:00Z", "ended_at": "2026-07-01T12:00:02Z", "task_input": "Where is order 88421?", "final_output": "Your order 88421 is in transit.", "steps": [{"index": 0, "kind": "llm", "llm": {"span_id": "s1", "model": "gpt-4o-mini", "input_messages": [{"role": "user", "content": "Where is order 88421?"}], "output_message": {"role": "assistant", "content": "Let me look that up."}}}, {"index": 1, "kind": "tool", "tool": {"span_id": "s2", "name": "order_lookup", "arguments_json": "{\"order_id\": \"88421\"}", "output": "status: in_transit", "latency_ms": 142.0}}]}
```

Annotations: `arguments_json` is a raw JSON *string* (never a parsed object), so nothing is lost in translation. `output_message`, `model`, token counts, and `latency_ms` are all optional.

### Example: failure trace (tool step with `error` set)

```json
{"trace_id": "tr-fail-1", "source": "generic", "started_at": "2026-07-01T12:05:00Z", "ended_at": "2026-07-01T12:05:01Z", "task_input": "Refund order 88421", "final_output": "Error: refund service unavailable.", "steps": [{"index": 0, "kind": "tool", "tool": {"span_id": "s3", "name": "refund_api", "arguments_json": "{\"order_id\": \"88421\"}", "output": null, "error": "HTTP 503 Service Unavailable"}}]}
```

A non-null `tool.error` makes the built-in `R_TOOL_ERROR` rule label the trace `tool_error`, which is what routes it into a failure cluster and, with `--include-failures`, into a regression case.

### Assumptions & Heuristics
- Direct structural validation, no field inference.
- Lines failing to parse are logged as warnings and skipped; the ingest never aborts.

---

## 2. OpenTelemetry GenAI Conventions (`otel`)

OTel traces are ingested from flat lists of JSON span logs (e.g. OTLP export format), grouped by `trace_id`.

### Span Categorization Rules
- **Root Span**: Identified by `parent_span_id` being `None` or empty.
- **LLM Call**: Spans containing GenAI semantic convention keys in their attributes:
  - `gen_ai.system`
  - `gen_ai.prompt`
  - `gen_ai.completion`
- **Tool Call**: Spans matching any of these signals:
  - `gen_ai.tool.name` present in attributes (primary, per GenAI semantic conventions)
  - `gen_ai.tool.arguments` present in attributes
  - `gen_ai.operation.name` attribute equal to `"execute_tool"`
  - `tool.name` present in attributes
  - Span name matches a user-supplied glob from `traceval ingest --tool-span-names` (comma-separated, e.g. `"*_lookup,tool_*"`)

  There is no built-in tool-name list; detection never depends on a specific tool vocabulary.
- **Other**: All other spans are categorized as `other`.

### Attribute Translations

| Canonical Field | OTel Span Path |
| --- | --- |
| `started_at` | Root span `start_time` (ISO datetime) |
| `ended_at` | Root span `end_time` (ISO datetime) |
| `task_input` | Root span `attributes["gen_ai.task_input"]` |
| `final_output` | Root span `attributes["gen_ai.final_output"]` |
| `llm.model` | Span `attributes["gen_ai.request.model"]` |
| `llm.input_messages` | Parsed JSON array from `attributes["gen_ai.prompt"]` |
| `llm.output_message` | Assistant role with content from `attributes["gen_ai.completion"]` |
| `llm.prompt_tokens` | `attributes["gen_ai.usage.prompt_tokens"]` |
| `llm.completion_tokens` | `attributes["gen_ai.usage.completion_tokens"]` |
| `llm.error` | `attributes["gen_ai.error"]` |
| `tool.name` | `attributes["gen_ai.tool.name"]` or Span `name` |
| `tool.arguments_json` | `attributes["gen_ai.tool.arguments"]` |
| `tool.output` | `attributes["gen_ai.tool.output"]` |
| `tool.error` | `attributes["gen_ai.tool.error"]` or `attributes["gen_ai.error"]` |

---

## 3. Langfuse Export (`langfuse`)

Langfuse exports traces as JSON objects with nested lists of observations (of types `GENERATION`, `SPAN`, `EVENT`).

### Mapping Translations

| Canonical Field | Langfuse Path |
| --- | --- |
| `trace_id` | Trace `id` |
| `started_at` | Trace `timestamp` |
| `ended_at` | Trace `timestamp` + `latency` (the export carries `latency` in seconds, not an end time) |
| `task_input` | Trace `input` |
| `final_output` | Trace `output` |
| `metadata` | Trace `metadata` |

> Note: Langfuse has deprecated trace-level `input`/`output` (v4.13 steers to `propagate_attributes()`). The adapter still reads them for `task_input`/`final_output`; a fallback to the root span's input/output is tracked as a follow-up issue.

### Root span handling

Modern Langfuse SDKs (the `@observe` decorator) emit the entry function itself as a root SPAN inside the flat `observations` list, with the trace's input and output on it. That root is the trace envelope, not a tool call, so the adapter skips it when it is a null-`parentObservationId` SPAN that is either referenced as a parent by another observation OR whose `name` matches the trace name (which covers a trace that failed before any child observation). Older flat exports have neither signal, so nothing is skipped there.

### Observation Mapping
- **GENERATION** $\rightarrow$ `LLMCall`:
  - `llm.model` $\leftarrow$ Observation `model`
  - `llm.input_messages` $\leftarrow$ Observation `input` (parsed list of message objects)
  - `llm.output_message` $\leftarrow$ Observation `output`
  - `llm.prompt_tokens` $\leftarrow$ `usage.promptTokens`
  - `llm.completion_tokens` $\leftarrow$ `usage.completionTokens`
  - `llm.error` $\leftarrow$ `statusMessage` when `level == "ERROR"`
- **SPAN** $\rightarrow$ `ToolCall` when, in priority order:
  1. the observation's `metadata.tool` is set (explicit marker, always wins), or
  2. `traceval ingest --tool-span-names` globs were supplied and the observation `name` matches one (globs replace the heuristic below), or
  3. default heuristic: the SPAN recorded an `input` AND either an `output` or an error signal (`level == "ERROR"` or `statusMessage` set). Failed tool calls often produce no output, which is why an error counts as the second signal.

  SPANs matching none of these become `other` steps. Field mapping:
  - `tool.name` $\leftarrow$ Observation `name`
  - `tool.arguments_json` $\leftarrow$ Observation `input` (serialized to JSON)
  - `tool.output` $\leftarrow$ Observation `output` (stringified)
  - `tool.error` $\leftarrow$ `statusMessage` when `level == "ERROR"`

---

## 4. LangSmith Run Export (`langsmith`)

LangSmith exports represent hierarchical run hierarchies grouped by `trace_id`.

`--tool-span-names` has no effect here; LangSmith's explicit `run_type` field makes the heuristic unnecessary.

### Mapping Translations

| Canonical Field | LangSmith Path |
| --- | --- |
| `trace_id` | Run `trace_id` or root run `id` |
| `started_at` | Root run `start_time` |
| `ended_at` | Root run `end_time` |
| `task_input` | Root run `inputs["input"]` or first key's value |
| `final_output` | Root run `outputs["output"]` or first key's value |

### Child Run Classification
- **run_type == "llm"** $\rightarrow$ `LLMCall`:
  - `llm.model` $\leftarrow$ `extra.metadata.ls_model_name`
  - `llm.input_messages` $\leftarrow$ `inputs.messages` (list mapping)
  - `llm.output_message` $\leftarrow$ First element of `outputs.generations`
  - `llm.prompt_tokens` $\leftarrow$ `extra.token_usage.prompt_tokens`
  - `llm.completion_tokens` $\leftarrow$ `extra.token_usage.completion_tokens`
  - `llm.error` $\leftarrow$ Run `error` field
- **run_type == "tool"** $\rightarrow$ `ToolCall`:
  - `tool.name` $\leftarrow$ Run `name`
  - `tool.arguments_json` $\leftarrow$ Serialized run `inputs` dict
  - `tool.output` $\leftarrow$ Run `outputs["output"]` or serialized outputs
  - `tool.error` $\leftarrow$ Run `error` field
