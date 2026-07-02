# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.5] - 2026-07-02

### Changed
- Corrected the author email in the package metadata; added the demo GIF to the README (generated with `make demo-gif`).

## [0.2.4] - 2026-07-02

### Changed
- **PyPI page**: real package metadata (selling one-line summary, project URLs, author, keywords, classifiers including `Typing :: Typed` backed by a `py.typed` marker in the wheel) and a README whose image and doc links are absolute URLs, so the PyPI page renders correctly (verified with readme-renderer).
- **Unified CLI color scheme**: one shared console with a semantic palette (green passed, red failed, yellow errored/warnings, cyan paths, magenta clusters, bold counts and headings, bold-red errors on stderr) across ingest/analyze/generate/demo/serve/calibrate and the generated run summary. Styling auto-disables when the stream is not a TTY and honors `NO_COLOR`; `--json` output bypasses the console entirely and is byte-identical (pinned by tests).
- Ingest shows a progress bar when stdout is a TTY and `--json` is not set; never in pipes or CI.

### Added
- `docs/demo.tape` (vhs script) and `make demo-gif` to record the demo GIF for the README; the embed ships commented-out until the GIF is generated and committed. The three doc papercuts from the last audit (LangSmith flag note, FastAPI example prerequisites, pip fallback in CONTRIBUTING) were verified already shipped on main after the v0.2.3 tag.

## [0.2.3] - 2026-07-02

### Fixed
- **Adapter tool detection no longer depends on demo tool names.** The Langfuse and OTel adapters matched span names against the demo agent's tool vocabulary (`order_lookup`, `stripe_lookup`, `kb_search`), so real exports with any other tool names silently classified tool spans as `other`, breaking `tool_error` labeling, `tool_sequence`/`no_tool_loop` generation, and cluster signatures. Langfuse SPANs now classify via `metadata.tool`, user-supplied `--tool-span-names` globs, or a documented input+output/error heuristic; OTel uses GenAI semantic-convention attributes with attribute-only fallbacks. Detection is proven vocabulary-free by new `create_ticket` fixtures. Surfaced by external review, found by reading; a real export would have found it in seconds.
- Sub-millisecond latencies render as `<0.1` in the run summary instead of `0.0`.

### Added
- `traceval ingest --tool-span-names`: comma-separated name globs marking spans as tool calls (replaces the Langfuse heuristic, adds an OTel fallback).
- `docs/targets.md`: the exact run-against-my-agent contract (HTTP request/response shape, callable return shapes, timeout and failure behavior) with an executable FastAPI example.
- `docs/extending.md`: custom outcome rules, redaction hook, judge configuration as implemented, and an honest `traceval.yaml` reference.
- `docs/formats.md`: complete annotated generic-format examples (success and tool-failure lines that ingest as-is) and a required-vs-optional field table; Langfuse/OTel sections rewritten to match the new heuristics.

## [0.2.2] - 2026-07-02

### Fixed
- A run in which zero cases execute (e.g. unresolvable target) now writes a self-describing run report with an `errors` section instead of writing nothing; `--json` never reports `null`. Added a single clear top-level error line on target-resolution failure. Added `make test` and CONTRIBUTING as the canonical dev commands. Reported via external review of a failed-target invocation.
- Run report schema additions (existing fields unchanged): `summary.errored` counts cases that never executed due to setup/collection errors; top-level `errors` lists `{stage, detail}` entries for `target_resolution`, `collection`, and `setup` failures, with identical details deduplicated into one entry carrying a `count`; `results` is `[]` rather than absent when nothing executed. The terminal summary now shows `Errored: n`.

## [0.2.1] - 2026-07-02

### Added
- `--json` on `ingest`, `analyze`, `generate`, and `run`: suppresses human-readable output and prints a single JSON object to stdout for scripting (`run` still exits nonzero on failures). The README previously claimed this flag existed; now it does.
- `traceval demo`: runs the full trace-to-eval loop end-to-end with a built-in demo agent from a plain pip install (no repo clone). Creates `./traceval-demo/` (override with `-o`), refuses to write into a non-empty directory unless `--force`, and `--force` only ever replaces the demo's own artifacts. The demo agent and trace generator moved into the package (`traceval.demo`); `examples/` keeps thin wrappers.
- `traceval serve [dir]`: serves the analysis report directory on localhost with Python's stdlib http.server and prints the report URL. Not a web UI.
- Generated `test_generated.py` opens with the three commands a new teammate needs; the run summary ends with a `traceval calibrate` hint for the report just written.
- CI: wheel-based demo smoke job (build wheel, install into a clean venv, run `traceval demo` from an empty directory) so the pip-user path is what CI tests. Releases now gate on it.

### Changed
- Failure-signature tokens for `not_contains` checks are now distinctiveness-filtered: a token qualifies only if it appears in fewer than 10% of success outputs (same-cluster successes preferred, all successes in the db as fallback). If no token survives, the check is omitted rather than emitting a junk forbidden list.
- `not_contains` matching is word-boundary based and case-insensitive instead of raw substring: forbidding "error" no longer false-fails a healthy "no errors found".
- README rewritten: real command outputs (regenerable via `scripts/readme-outputs.sh`), a live screenshot of the analysis report, evidence-based feature claims, plain pipeline diagram, and the GitHub Action example pinned to a release tag.

### Fixed
- Generated run summary printed a literal `\n` before "traceval Run Summary" (jinja over-escaping in the conftest template).
- `analysis/report.html` version badge was hardcoded to v0.1.0; it now shows the installed traceval version.

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
- **Regression-case semantics inverted (correctness bug)**: cases generated from failure traces used to copy `contains_any`/`tool_sequence`/`json_schema` checks from the failure itself, demanding the agent *reproduce* the bug. Regression cases now assert failure **absence**: `not_contains` with error-signature tokens (input-echo tokens excluded), `no_tool_loop` for loop failures, and a non-empty-output check for timeouts. The failure output no longer leaks into `reference_output` (it would poison LLM-judge grading); it is preserved in the case notes for reviewers. Note: regression cases pass for any agent that avoids the recorded failure mode; golden cases carry general bug detection.
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
