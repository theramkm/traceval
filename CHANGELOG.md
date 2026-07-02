# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-02

### Added
- **Canonical Model & SQLite Storage**: Structured canonical schema representing `Trace`, `Step`, `ToolCall`, `LLMCall`, and `Outcome`.
- **Multi-backend Telemetry Ingestion**: Added log adapters for OpenTelemetry GenAI, Langfuse observation dumps, LangSmith logs, and Generic JSONL files.
- **Rule-based Labeler**: Dynamic outcome labels classifier (`success`, `tool_error`, `validation_error`, `loop`, `timeout`, `bad_output`, `unknown`) with custom python rule plugins.
- **Agglomerative Clustering**: Signature and task-input Jaccard shingle clustering.
- **Jinja2 Coverage Report Visualizer**: Ported self-contained single-page HTML report charts.
- **Pytest Case Compiler**: Emitter of YAML test case configurations, LLM-as-judge scaffolds, and custom redact hook scrubbers.
- **Scorers & Judges**: Scorer implementations for `exact`, `contains`, `regex`, `json_schema`, `tool_sequence` (order/subset modes), and `judge` (FakeJudge, OpenAICompatJudge with call caps).
- **FastAPI Demo Agent**: Supporting mock customer service tools and BUGGY mode regressions checks.
