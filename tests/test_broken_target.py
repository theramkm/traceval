"""Regression tests for the failed-target incident: a run in which zero
cases execute must write a self-describing run report, print one clear
error line, and never report null. Silence is the bug.

Reported via external review of a failed-target invocation.
"""

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from traceval.cli import app
from traceval.compile import generate_evals
from traceval.ingest import ingest_file
from traceval.store import TraceStore

FIXTURES_DIR = Path(__file__).parent / "fixtures"
BROKEN_TARGET = "no.such.module:fn"

runner = CliRunner()


def _generate_suite(tmp_path):
    db_path = tmp_path / "traces.db"
    store = TraceStore(db_path)
    ingest_file(FIXTURES_DIR / "generic_traces.jsonl", store, format_name="generic")
    store.close()
    evals_dir = tmp_path / "evals"
    generate_evals(db_path, evals_dir, include_failures=True)
    return evals_dir


def _run(evals_dir, *extra_args):
    # `run` calls pytest.main in-process; a previously executed generated
    # suite leaves its conftest cached in sys.modules and poisons this one.
    for mod in ("conftest", "test_generated"):
        sys.modules.pop(mod, None)
    return runner.invoke(
        app,
        [
            "run",
            str(evals_dir),
            "--target",
            BROKEN_TARGET,
            "--judge",
            "fake",
            *extra_args,
        ],
    )


def test_broken_target_writes_report(tmp_path):
    evals_dir = _generate_suite(tmp_path)
    result = _run(evals_dir)
    assert result.exit_code != 0

    reports = list((evals_dir / "runs").glob("run_*.json"))
    assert len(reports) == 1, "exactly one report must be written"

    with open(reports[0], encoding="utf-8") as f:
        report = json.load(f)
    assert report["summary"]["errored"] == report["summary"]["total"] > 0
    assert report["summary"]["passed"] == 0
    assert report["summary"]["failed"] == 0
    assert report["results"] == []
    assert report["errors"][0]["stage"] == "target_resolution"
    assert BROKEN_TARGET in report["errors"][0]["detail"]
    # Identical per-case setup errors deduplicate into one counted entry
    setup_errors = [e for e in report["errors"] if e["stage"] == "setup"]
    assert len(setup_errors) == 1
    assert setup_errors[0]["count"] == report["summary"]["errored"]


def test_broken_target_json_report_not_null(tmp_path):
    evals_dir = _generate_suite(tmp_path)
    result = _run(evals_dir, "--json")
    data = json.loads(result.stdout)
    assert isinstance(data["report"], str)
    assert Path(data["report"]).exists()
    assert data["exit_code"] == 1
    assert result.exit_code == 1


def test_broken_target_prints_one_clear_error(tmp_path):
    evals_dir = _generate_suite(tmp_path)
    result = _run(evals_dir)
    error_line = f"ERROR: target '{BROKEN_TARGET}' could not be imported"
    assert result.output.count(error_line) == 1, result.output
