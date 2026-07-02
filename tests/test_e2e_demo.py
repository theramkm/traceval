"""The flagship-workflow e2e: generate evals from traces, then verify the
healthy demo agent PASSES its own generated suite and the buggy one FAILS.

This is the test that guards the core product promise. It must never be
replaced by a static-fixture assertion.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from traceval.compile import generate_evals
from traceval.ingest import ingest_file
from traceval.store import TraceStore

REPO_ROOT = Path(__file__).parent.parent
SYNTHETIC_TRACES = REPO_ROOT / "examples" / "synthetic_traces.jsonl"


@pytest.fixture(scope="module")
def generated_suite(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("e2e")
    db_path = tmp_path / "traces.db"
    store = TraceStore(db_path)
    ingest_file(SYNTHETIC_TRACES, store, format_name="generic")
    store.close()

    evals_dir = tmp_path / "evals"
    generate_evals(db_path, evals_dir, include_failures=True)
    return evals_dir


def _run_suite(evals_dir: Path, buggy: bool) -> subprocess.CompletedProcess:
    # Subprocess on purpose: the generated suite imports its own conftest by
    # module name and the judge call budget is process-global, so two runs in
    # one process would collide. BUGGY is scoped to the child env.
    env = {**os.environ, "BUGGY": "true" if buggy else "false"}
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(evals_dir),
            "--target",
            "examples.demo_agent.core:invoke_agent",
            "--judge",
            "fake",
            "-p",
            "no:cacheprovider",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def _latest_report(evals_dir: Path) -> dict:
    reports = sorted((evals_dir / "runs").glob("run_*.json"))
    assert reports, "run report must be written inside the evals dir"
    with open(reports[-1], encoding="utf-8") as f:
        return json.load(f)


def test_healthy_agent_passes_generated_suite(generated_suite):
    result = _run_suite(generated_suite, buggy=False)
    assert result.returncode == 0, (
        "Healthy agent must pass its own generated eval suite.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    report = _latest_report(generated_suite)
    assert report["summary"]["failed"] == 0
    assert report["summary"]["passed"] == report["summary"]["total"] > 0


def test_buggy_agent_fails_generated_suite(generated_suite):
    result = _run_suite(generated_suite, buggy=True)
    assert result.returncode == 1, (
        "Buggy agent must fail the generated eval suite.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    report = _latest_report(generated_suite)
    assert report["summary"]["failed"] > 0

    # Golden cases carry general bug detection (regression cases only bite on
    # the recorded failure mode): at least one failed case must be a golden.
    kind_by_id = {}
    for case_file in (generated_suite / "cases").rglob("*.yaml"):
        with open(case_file, encoding="utf-8") as f:
            case = yaml.safe_load(f)
        kind_by_id[case["id"]] = case["kind"]
    failed_ids = [r["case_id"] for r in report["results"] if not r["passed"]]
    assert any(kind_by_id[cid] == "golden" for cid in failed_ids)
