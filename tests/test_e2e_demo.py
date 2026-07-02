"""The flagship-workflow e2e: `traceval demo` runs the whole loop with the
packaged demo agent and asserts the core promise itself, healthy agent
passes the generated suite, buggy agent fails it.

This is the test that guards the product headline. It must never be
replaced by a static-fixture assertion.
"""

import json

import yaml
from typer.testing import CliRunner

from traceval.cli import app

runner = CliRunner()


def test_demo_end_to_end(tmp_path):
    demo_dir = tmp_path / "demo"
    result = runner.invoke(app, ["demo", "-o", str(demo_dir)])
    assert result.exit_code == 0, result.output

    assert "healthy agent PASSED, buggy agent FAILED" in result.output
    # The closing summary teaches the manual commands
    assert "traceval calibrate" in result.output

    # Two run reports: healthy first, buggy second
    reports = sorted((demo_dir / "evals" / "runs").glob("run_*.json"))
    assert len(reports) == 2
    with open(reports[0], encoding="utf-8") as f:
        healthy = json.load(f)
    with open(reports[1], encoding="utf-8") as f:
        buggy = json.load(f)

    assert healthy["summary"]["failed"] == 0
    assert healthy["summary"]["passed"] == healthy["summary"]["total"] > 0
    assert buggy["summary"]["failed"] > 0

    # Golden cases carry general bug detection (regression cases only bite on
    # the recorded failure mode): at least one failed case must be a golden.
    kind_by_id = {}
    for case_file in (demo_dir / "evals" / "cases").rglob("*.yaml"):
        with open(case_file, encoding="utf-8") as f:
            case = yaml.safe_load(f)
        kind_by_id[case["id"]] = case["kind"]
    failed_ids = [r["case_id"] for r in buggy["results"] if not r["passed"]]
    assert any(kind_by_id[cid] == "golden" for cid in failed_ids)

    # The analysis report exists for the user to open
    assert (demo_dir / "analysis" / "report.html").exists()


def test_demo_refuses_non_empty_dir_without_force(tmp_path):
    demo_dir = tmp_path / "demo"
    demo_dir.mkdir()
    precious = demo_dir / "precious.txt"
    precious.write_text("user data", encoding="utf-8")

    result = runner.invoke(app, ["demo", "-o", str(demo_dir)])
    assert result.exit_code == 1
    assert precious.read_text(encoding="utf-8") == "user data"

    # --force refreshes demo artifacts but never touches user files
    result = runner.invoke(app, ["demo", "-o", str(demo_dir), "--force"])
    assert result.exit_code == 0, result.output
    assert precious.read_text(encoding="utf-8") == "user data"
