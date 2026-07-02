# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-07-02

### Added
- **`traceval calibrate`**: validate the LLM judge against human labels. Samples judge-scored results from a run report (deterministic via `--seed`), presents each agent output for blind pass/fail labeling in the terminal (judge verdicts hidden until the end), then reports judge-vs-human agreement overall and per cluster with false-pass/false-fail counts, flagging clusters below `--min-agreement` (default 80%). Writes a `calibration.json` with stats and labels.

### Changed
- **Run report schema**: result items now include `input`, `output` (the agent's response), and `kind` (golden/regression), which calibrate requires. Reports written by older suites still load everywhere else; `calibrate` asks you to regenerate the suite when these fields are missing.

## [0.1.4] - 2026-07-02

### Added
- **GitHub Action** (`action.yml`): gate CI on your generated eval suite with `uses: theramkm/traceval@main`. Inputs: `evals-dir`, `target` (required); `judge`, `compare`, `only`, `runs-dir`, `traceval-version`, `python-version` (optional). The job fails whenever `traceval run` exits nonzero. Dogfooded in this repo's CI: the action runs the demo suite against the healthy agent (must pass) and the buggy agent (must fail), and releases are gated on it.

### Changed
- `pytest` is now a runtime dependency (was dev-only): `traceval run` executes the generated suite via pytest, so a plain `pip install traceval` now supports the full workflow.

## [0.1.3] - 2026-07-02

### Fixed
- **Cluster over-fragmentation**: digit-only tokens (order ids, amounts) are now collapsed to a `<num>` placeholder when building similarity shingles, so "Where is order 57978?" and "Where is order 12345?" cluster together. The 200-trace synthetic example now yields 8 clusters (4 intents + 4 failure modes) instead of 30+. Numeric tokens are also excluded from TF-IDF cluster naming and from case dedup shingles. Literal tokenization used for check inference is unchanged.

### Changed
- Cluster ids are content hashes of member trace ids, so existing cluster ids and rubric filenames will change after upgrading; regenerate suites with `traceval generate`.

## [0.1.2] - 2026-07-02

### Fixed
- **Regression-case semantics inverted (correctness bug)**: cases generated from failure traces used to copy `contains_any`/`tool_sequence`/`json_schema` checks from the failure itself, demanding the agent *reproduce* the bug. Regression cases now assert failure **absence**: `not_contains` with error-signature tokens (input-echo tokens excluded), `no_tool_loop` for loop failures, and a non-empty-output check for timeouts. The failure output no longer leaks into `reference_output` (it would poison LLM-judge grading); it is preserved in the case notes for reviewers. Note: regression cases pass for any agent that avoids the recorded failure mode — golden cases carry general bug detection.
- **FakeJudge vs generated `min_score` mismatch**: FakeJudge's neutral score (0.5) failed the generated judge threshold (0.7) by construction, so offline runs (`--judge fake`) could never pass. The neutral score is now 0.7: with the fake judge, deterministic checks gate the run, judge checks do not.
- **Run reports** are now written inside `<evals_dir>/runs/` (previously the evals dir's *parent*, which could land in the invocation cwd), with a `--runs-dir` override on `traceval run`. Report filenames now carry microsecond timestamps so back-to-back runs (e.g. `--compare` workflows) cannot overwrite each other.
- `examples.demo_agent.agent` re-exports `invoke_agent` again (lost in the `core.py` split); demo/docs now target `examples.demo_agent.core:invoke_agent`, which needs no FastAPI install.
- `examples/make_traces.py` is now deterministic (seeded RNG, fixed base timestamp).

### Added
- New check types: `not_contains` (fails if any forbidden value appears in the output) and `no_tool_loop` (fails if any tool is called N+ times consecutively; default 3). Note: older traceval versions silently skip unknown check types, so suites using these checks need >= 0.1.2 to enforce them.
- Real end-to-end test (`tests/test_e2e_demo.py`): generates the eval suite from the demo traces, asserts the healthy agent passes it (exit 0) and the buggy agent fails it (exit 1). Rubrics for failure-dominated clusters now include an explicit "must NOT exhibit failure mode" criterion.

## [0.1.1] - 2026-07-02

### Changed
- Version bump for the initial PyPI release; no functional changes.

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
