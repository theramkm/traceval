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

A line-by-line JSONL file where each line is a raw JSON string validating directly against our canonical `Trace` model.

### Assumptions & Heuristics
- Direct structural validation.
- Lines failing to parse are logged as warnings and skipped.

---

## 2. OpenTelemetry GenAI Conventions (`otel`)

OTel traces are ingested from flat lists of JSON span logs (e.g. OTLP export format), grouped by `trace_id`.

### Span Categorization Rules
- **Root Span**: Identified by `parent_span_id` being `None` or empty.
- **LLM Call**: Spans containing GenAI semantic convention keys in their attributes:
  - `gen_ai.system`
  - `gen_ai.prompt`
  - `gen_ai.completion`
- **Tool Call**: Spans containing:
  - `gen_ai.tool.name`
  - `gen_ai.tool.arguments`
  - Or span name matching `order_lookup`, `stripe_lookup`, or `kb_search`.
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
| `task_input` | Trace `input` |
| `final_output` | Trace `output` |
| `metadata` | Trace `metadata` |

### Observation Mapping
- **GENERATION** $\rightarrow$ `LLMCall`:
  - `llm.model` $\leftarrow$ Observation `model`
  - `llm.input_messages` $\leftarrow$ Observation `input` (parsed list of message objects)
  - `llm.output_message` $\leftarrow$ Observation `output`
  - `llm.prompt_tokens` $\leftarrow$ `usage.promptTokens`
  - `llm.completion_tokens` $\leftarrow$ `usage.completionTokens`
  - `llm.error` $\leftarrow$ `statusMessage` when `level == "ERROR"`
- **SPAN** $\rightarrow$ `ToolCall` (if name is order/stripe/kb lookup or `metadata.tool` matches):
  - `tool.name` $\leftarrow$ Observation `name`
  - `tool.arguments_json` $\leftarrow$ Observation `input` (serialized to JSON)
  - `tool.output` $\leftarrow$ Observation `output` (stringified)
  - `tool.error` $\leftarrow$ `statusMessage` when `level == "ERROR"`

---

## 4. LangSmith Run Export (`langsmith`)

LangSmith exports represent hierarchical run hierarchies grouped by `trace_id`.

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
