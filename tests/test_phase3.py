from pathlib import Path

from typer.testing import CliRunner

from traceval.analyze import run_analysis
from traceval.cli import app
from traceval.ingest import ingest_file
from traceval.store import TraceStore

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"


def test_builtin_outcome_labeling(tmp_path):
    db_path = tmp_path / "test.db"
    store = TraceStore(db_path)

    # Ingest generic traces
    ingest_file(FIXTURES_DIR / "generic_traces.jsonl", store, format_name="generic")

    # Run analysis
    run_analysis(db_path)

    # Check that labels match stories
    # tr-001: success (R_DEFAULT_SUCCESS)
    # tr-002: tool_error (R_TOOL_ERROR)
    # tr-003: bad_output (R_LLM_ERROR)
    # tr-004: loop (R_LOOP)
    # tr-005: timeout (R_TIMEOUT)
    # tr-006: validation_error (R_VALIDATION)
    # tr-007: bad_output (R_EMPTY_OUTPUT)
    # tr-008: success (R_DEFAULT_SUCCESS)
    # tr-009: unknown (R_UNKNOWN)

    t1 = store.get_trace("tr-001")
    assert t1.outcome.label == "success"
    assert t1.outcome.rule_id == "R_DEFAULT_SUCCESS"

    t2 = store.get_trace("tr-002")
    assert t2.outcome.label == "tool_error"
    assert t2.outcome.rule_id == "R_TOOL_ERROR"

    t3 = store.get_trace("tr-003")
    assert t3.outcome.label == "bad_output"
    assert t3.outcome.rule_id == "R_LLM_ERROR"

    t4 = store.get_trace("tr-004")
    assert t4.outcome.label == "loop"
    assert t4.outcome.rule_id == "R_LOOP"

    t5 = store.get_trace("tr-005")
    assert t5.outcome.label == "timeout"
    assert t5.outcome.rule_id == "R_TIMEOUT"

    t6 = store.get_trace("tr-006")
    assert t6.outcome.label == "validation_error"
    assert t6.outcome.rule_id == "R_VALIDATION"

    t7 = store.get_trace("tr-007")
    assert t7.outcome.label == "bad_output"
    assert t7.outcome.rule_id == "R_EMPTY_OUTPUT"

    t8 = store.get_trace("tr-008")
    assert t8.outcome.label == "success"

    store.close()


def test_custom_rule_override(tmp_path):
    # Create temporary rules file
    rules_file = tmp_path / "my_rules.py"
    rules_file.write_text(
        """
from traceval.model import Trace, Outcome
from traceval.analyze.outcomes import Rule

def custom_override(trace: Trace) -> Outcome | None:
    if "Where is my order" in trace.task_input:
        return Outcome(
            label="bad_output",
            reason="custom override rule triggered",
            labeled_by="user_rule",
            rule_id="R_MY_OVERRIDE"
        )
    return None

RULES = [
    Rule("R_MY_OVERRIDE", "Override order queries", custom_override)
]
""",
        encoding="utf-8",
    )

    db_path = tmp_path / "test.db"
    store = TraceStore(db_path)
    ingest_file(FIXTURES_DIR / "generic_traces.jsonl", store, format_name="generic")

    # Run analysis with custom rules
    run_analysis(db_path, rules_path=rules_file)

    # tr-001 has input "Where is my order 12345?" and should be overridden to bad_output
    t1 = store.get_trace("tr-001")
    assert t1.outcome.label == "bad_output"
    assert t1.outcome.labeled_by == "user_rule"
    assert t1.outcome.rule_id == "R_MY_OVERRIDE"

    store.close()


def test_clustering_determinism(tmp_path):
    db_path = tmp_path / "test.db"
    store = TraceStore(db_path)
    ingest_file(FIXTURES_DIR / "generic_traces.jsonl", store, format_name="generic")

    # Run analysis
    res1 = run_analysis(db_path)
    res2 = run_analysis(db_path)

    # Determinism assertion: structure is identical across runs
    assert res1["clusters"] == res2["clusters"]
    store.close()


def test_cli_analyze(tmp_path):
    fixture_path = FIXTURES_DIR / "generic_traces.jsonl"
    db_path = tmp_path / "cli_test.db"
    analysis_dir = tmp_path / "analysis"

    runner = CliRunner()
    # 1. Ingest
    runner.invoke(
        app,
        ["ingest", str(fixture_path), "-o", str(db_path), "--format", "generic"],
    )
    # 2. Analyze
    result = runner.invoke(
        app,
        ["analyze", str(db_path), "-o", str(analysis_dir)],
    )

    assert result.exit_code == 0
    assert "Outcomes:" in result.stdout
    assert "Clusters:" in result.stdout
    assert (analysis_dir / "report.json").exists()
