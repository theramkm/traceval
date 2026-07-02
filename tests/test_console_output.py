"""Styled CLI output must degrade to plain text for machines.

rich auto-disables styling when the stream is not a TTY and honors
NO_COLOR; these tests pin that no ANSI escape codes reach captured
output, and that --json stdout stays pure JSON.
"""

import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from traceval.cli import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"
ANSI_ESCAPE = "\x1b["

runner = CliRunner()


def _ingested_db(tmp_path):
    db_path = tmp_path / "t.db"
    result = runner.invoke(
        app,
        [
            "ingest",
            str(FIXTURES_DIR / "generic_traces.jsonl"),
            "-o",
            str(db_path),
            "--format",
            "generic",
        ],
    )
    assert result.exit_code == 0
    return db_path, result


def test_captured_output_has_no_ansi_codes(tmp_path):
    db_path, ingest_result = _ingested_db(tmp_path)
    assert ANSI_ESCAPE not in ingest_result.output

    analyze_result = runner.invoke(
        app, ["analyze", str(db_path), "-o", str(tmp_path / "analysis")]
    )
    assert analyze_result.exit_code == 0
    assert "Outcomes:" in analyze_result.output
    assert ANSI_ESCAPE not in analyze_result.output

    generate_result = runner.invoke(
        app,
        ["generate", str(db_path), "-o", str(tmp_path / "evals"), "--include-failures"],
    )
    assert generate_result.exit_code == 0
    assert ANSI_ESCAPE not in generate_result.output


def test_no_color_env_pipe_has_no_ansi_codes(tmp_path):
    db_path, _ = _ingested_db(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "traceval.cli",
            "analyze",
            str(db_path),
            "-o",
            str(tmp_path / "analysis"),
        ],
        capture_output=True,
        text=True,
        env={"NO_COLOR": "1", "PATH": "/usr/bin:/bin", "PYTHONPATH": "src"},
        cwd=Path(__file__).parent.parent,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Outcomes:" in proc.stdout
    assert ANSI_ESCAPE not in proc.stdout


def test_json_output_is_pure_json(tmp_path):
    db_path, _ = _ingested_db(tmp_path)
    result = runner.invoke(
        app, ["analyze", str(db_path), "-o", str(tmp_path / "analysis"), "--json"]
    )
    assert result.exit_code == 0
    # The whole of stdout is exactly one JSON object, no styling, no extras
    json.loads(result.stdout)
    assert ANSI_ESCAPE not in result.stdout
