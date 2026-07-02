"""Every documented --json command must print one parseable JSON object."""

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from traceval.cli import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"

runner = CliRunner()


def _ingest(db_path):
    result = runner.invoke(
        app,
        [
            "ingest",
            str(FIXTURES_DIR / "generic_traces.jsonl"),
            "-o",
            str(db_path),
            "--format",
            "generic",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    return result


def test_ingest_json(tmp_path):
    result = _ingest(tmp_path / "t.db")
    data = json.loads(result.stdout)
    assert set(data) == {"traces", "spans", "warnings", "log", "db"}
    assert data["traces"] > 0
    assert data["db"] == str(tmp_path / "t.db")


def test_analyze_json(tmp_path):
    db_path = tmp_path / "t.db"
    _ingest(db_path)
    result = runner.invoke(
        app,
        ["analyze", str(db_path), "-o", str(tmp_path / "analysis"), "--json"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert set(data) == {
        "outcomes",
        "clusters",
        "top_failure_cluster",
        "report_html",
        "report_json",
    }
    assert 0 < sum(data["outcomes"].values()) <= 1.000001
    assert data["clusters"] > 0
    assert Path(data["report_json"]).exists()


def test_generate_json(tmp_path):
    db_path = tmp_path / "t.db"
    _ingest(db_path)
    result = runner.invoke(
        app,
        [
            "generate",
            str(db_path),
            "-o",
            str(tmp_path / "evals"),
            "--include-failures",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert set(data) == {"cases", "clusters", "golden", "regression", "output_dir"}
    assert data["golden"] + data["regression"] == data["cases"]
    assert data["regression"] > 0


def test_run_json(tmp_path):
    db_path = tmp_path / "t.db"
    _ingest(db_path)
    evals_dir = tmp_path / "evals"
    runner.invoke(
        app,
        ["generate", str(db_path), "-o", str(evals_dir), "--include-failures"],
    )
    # `run` calls pytest.main in-process; a previously executed generated
    # suite leaves its conftest cached in sys.modules and poisons this one.
    for mod in ("conftest", "test_generated"):
        sys.modules.pop(mod, None)
    result = runner.invoke(
        app,
        [
            "run",
            str(evals_dir),
            "--target",
            "tests.test_phase6:dummy_agent_fn",
            "--judge",
            "fake",
            "--json",
        ],
    )
    assert result.exit_code in (0, 1)
    data = json.loads(result.stdout)
    assert set(data) == {"total", "passed", "failed", "report", "exit_code"}
    assert data["total"] == data["passed"] + data["failed"]
    assert data["exit_code"] == result.exit_code
    assert Path(data["report"]).exists()
