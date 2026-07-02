# 🚀 traceval: Trace-to-Eval Compiler

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue.svg" alt="Python Version" />
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License" />
  <img src="https://img.shields.io/badge/Coverage-87%25-green.svg" alt="Coverage" />
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/dynamic/json?label=uv&query=%24.version&url=https%3A%2F%2Fraw.githubusercontent.com%2Fastral-sh%2Fuv%2Fmain%2Fcargo.toml&color=de5d43" alt="uv" /></a>
</p>

***"Your traces already know how your agent fails. traceval turns them into the test suite you never wrote."***

Teams running LLM agents in production have observability traces, but only a fraction maintain robust evals. The raw material for great tests, including thousands of real production traces with edge cases and errors, sits unused because converting them into regression suites is manual and tedious.

**traceval** automates this by ingesting agent traces from standard sources, normalizing them into a canonical Pydantic model, analyzing outcomes/clustering task signatures, and **compiling them into a human-editable eval suite**: pytest files + YAML datasets + judge rubric scaffolds.

---

## 🎨 Architectural Pipeline

```mermaid
graph LR
    classDef source fill:#2c3e50,stroke:#34495e,stroke-width:2px,color:#fff;
    classDef normalize fill:#16a085,stroke:#1abc9c,stroke-width:2px,color:#fff;
    classDef analyze fill:#2980b9,stroke:#3498db,stroke-width:2px,color:#fff;
    classDef compile fill:#8e44ad,stroke:#9b59b6,stroke-width:2px,color:#fff;
    classDef run fill:#d35400,stroke:#e67e22,stroke-width:2px,color:#fff;

    A[OTel / Langfuse / LangSmith] --> B(Canonical Trace DB)
    B --> C(Outcome Labeler & Jaccard Clusterer)
    C --> D(YAML cases + Pytest + Rubrics)
    D --> E(HTTP / Callable Runner & Diff Reports)

    class A source;
    class B normalize;
    class C analyze;
    class D compile;
    class E run;
```

---

## ✨ Key Features

* 🔌 **Zero-Configuration Ingest**: Direct compatibility with OpenTelemetry GenAI semantic conventions, Langfuse observations, LangSmith runs, or generic JSONL exports.
* 🧠 **Smart Outcome Taxonomy**: Automatic categorization of trace outcomes (`success`, `tool_error`, `validation_error`, `loop`, `timeout`, `bad_output`) using rule-based heuristics that you can extend with Python modules.
* 📊 **Embedding-Free Clustering**: Fast, local Jaccard-similarity shingle grouping that runs 100% offline, keeping your development cycle private and deterministic.
* 📝 **Clean Code Generation**: Compiles cases into editable YAML files, LLM-as-a-judge rubrics into Markdown checklist scaffolds, and pytest test runs into clean templates.
* ⚡ **PII Redaction Safeguards**: Automatically scrubs emails, credit cards, phone numbers, and API tokens before writing test inputs.
* 🛡️ **CI/CD Regression Diff**: Compares execution summaries and scores between runs using exit codes to catch agent failures before deploying.

---

## 📦 Installation

Install `traceval` directly from PyPI:

```bash
pip install traceval
```

Or using `uv` for faster virtual environment setups:

```bash
uv pip install traceval
```

---

## ⏱️ 90-Second E2E Quickstart

Experience `traceval` regression testing out of the box using our interactive demo script:

```bash
# Clone & run the demo
chmod +x examples/demo.sh
./examples/demo.sh
```

### Manual Walkthrough

#### 1. Ingest Observability Logs
```bash
# Seed 200 synthetic telemetry traces containing successes and failure edge cases
python3 examples/make_traces.py

# Ingest into SQLite database
traceval ingest examples/synthetic_traces.jsonl -o traces.db
```

#### 2. Label & Analyze Traffic Gaps
```bash
traceval analyze traces.db -o analysis/
```
*Outputs outcome statistics and generates `analysis/report.html` mapping traffic clusters:*
```text
Outcomes: success 60% · tool_error 15% · loop 10% · timeout 8% · validation_error 8%
Clusters: 37 task clusters found.
Top failure cluster: "500 refund stripe -> stripe_lookup -> (tool_error)" (30 traces)
Report written to analysis/report.html
```

#### 3. Compile Cases and Pytest Harness
```bash
traceval generate traces.db -o evals/ --include-failures
```
*Generates test parameters `evals/cases/` and rubric Markdown checklists `evals/rubrics/`.*

#### 4. Run Evaluations & Detect Regressions
```bash
# Run against the healthy agent (100% Pass)
traceval run evals/ --target examples.demo_agent.core:invoke_agent --judge fake

# Run against the buggy agent (Detects regressions and exits with status 1)
BUGGY=true traceval run evals/ --target examples.demo_agent.core:invoke_agent --judge fake
```

---

## 🛠️ CLI Command Reference

> [!NOTE]
> All CLI commands support `--json` to output machine-readable stdout for scripting.

### Ingestion
```bash
traceval ingest <path> --format [auto|otel|langfuse|langsmith|generic] -o <traces.db>
```
*Ingests telemetry log dumps losslessly. Malformed spans write warnings to `<traces.db>.log`.*

### Analysis
```bash
traceval analyze <traces.db> [--rules custom_rules.py] [--evals evals/] -o <analysis_dir/>
```
*Runs rule pipelines and Jaccard shingle similarity groupings.*

### Generation
```bash
traceval generate <traces.db> -o <evals_dir/> [--per-cluster 3] [--include-failures] [--redact-hook module:fn]
```
*Creates regression cases, Markdown LLM-judge checklists, and conftest runners.*

### Runner
```bash
traceval run <evals_dir/> --target <url|module:function> [--judge fake|openai] [--compare runs/prev.json] [--runs-dir path/]
```
*Executes tests, scores output constraints (`exact`, `contains`, `not_contains`, `regex`, `json_schema`, `tool_sequence`, `no_tool_loop`, `judge`), and writes run reports to `<evals_dir>/runs/` (override with `--runs-dir`).*

*Case kinds: `golden` cases assert the recorded successful behavior; `regression` cases (from failure traces) assert the failure does **not** recur — forbidden error tokens, no tool loops, non-empty output. A regression case passes for any agent that avoids that failure mode; goldens carry general bug detection.*

### Judge Calibration
```bash
traceval calibrate <evals_dir>/runs/run_<ts>.json [--sample 20] [--seed 0] [--min-agreement 0.8] [-o calibration.json]
```
*An LLM judge is only as good as its agreement with human expertise. `calibrate` samples judge-scored results from a run report, presents each agent output for **blind** human pass/fail labeling in the terminal (judge verdicts stay hidden until the end to avoid anchoring), then reports judge-vs-human agreement overall and per cluster — including **false-pass** counts (judge approved, human rejected: the dangerous direction) — and flags clusters below the agreement threshold whose rubrics need review.*

---

## 🛡️ GitHub Action

Gate deploys on your generated eval suite. The action installs traceval, runs the suite, and fails the job on any regression (`traceval run` exits nonzero):

```yaml
jobs:
  agent-evals:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: theramkm/traceval@main
        with:
          evals-dir: evals/
          target: myapp.agent:invoke_agent   # or an HTTP URL
          judge: fake                        # offline; use 'openai' with an API key for LLM judging
```

Inputs: `evals-dir` and `target` (required); `judge`, `compare`, `only`, `runs-dir`, `traceval-version`, `python-version` (optional). For a real LLM judge, set `judge: openai` and pass `OPENAI_API_KEY` (or `GEMINI_API_KEY`) via `env:` from your repository secrets.

---

## 💡 Honest Limitations

* **Side-Effect Free**: traceval assertions evaluate input/output matches. It does not attempt to replay side effects (e.g., updating database records) on mock tools.
* **Text Telemetry**: The canonical model is optimized for text logs. Image or multimodal payloads in traces are logged as references.
* **Static Visualization**: The coverage report is a portable, single-file HTML page. There is no hosted web service.
