"""Regression cases must assert failure ABSENCE, not reproduce the failure."""

from pathlib import Path

import yaml

from traceval.compile import generate_evals
from traceval.ingest import ingest_file
from traceval.store import TraceStore

REPO_ROOT = Path(__file__).parent.parent
SYNTHETIC_TRACES = REPO_ROOT / "examples" / "synthetic_traces.jsonl"


def _generate_cases(tmp_path):
    db_path = tmp_path / "traces.db"
    store = TraceStore(db_path)
    ingest_file(SYNTHETIC_TRACES, store, format_name="generic")
    store.close()

    evals_dir = tmp_path / "evals"
    generate_evals(db_path, evals_dir, include_failures=True)

    cases = []
    for case_file in sorted((evals_dir / "cases").rglob("*.yaml")):
        with open(case_file, encoding="utf-8") as f:
            cases.append(yaml.safe_load(f))
    return cases


def test_regression_cases_have_inverted_checks(tmp_path):
    cases = _generate_cases(tmp_path)
    regressions = [c for c in cases if c["kind"] == "regression"]
    assert regressions, "synthetic traces must yield regression cases"

    for case in regressions:
        check_types = [chk["type"] for chk in case["expected"]["checks"]]
        # Nothing copied from the failure as a positive expectation
        assert "contains_any" not in check_types, case["id"]
        assert "tool_sequence" not in check_types, case["id"]
        assert "json_schema" not in check_types, case["id"]
        # The failure output must not be handed to the judge as reference
        assert case["reference_output"] == "", case["id"]
        # Judge check is always present
        assert "judge" in check_types, case["id"]


def test_loop_regression_case(tmp_path):
    cases = _generate_cases(tmp_path)
    loop_cases = [
        c
        for c in cases
        if c["kind"] == "regression" and c["source_trace_id"].startswith("tr-loop")
    ]
    assert loop_cases

    case = loop_cases[0]
    checks = {chk["type"]: chk for chk in case["expected"]["checks"]}

    # Failure output "Failed execution due to system loop." becomes forbidden
    # tokens -- minus tokens echoed from the input ("execution") and short
    # generic words ("due").
    assert "not_contains" in checks
    forbidden = checks["not_contains"]["values"]
    assert "failed" in forbidden
    assert "execution" not in forbidden
    assert "due" not in forbidden

    # The recorded 4x order_lookup loop becomes a bound, not an expectation
    assert "no_tool_loop" in checks
    assert checks["no_tool_loop"]["max_repeats"] == 3


def test_timeout_regression_case_requires_output(tmp_path):
    cases = _generate_cases(tmp_path)
    timeout_cases = [
        c
        for c in cases
        if c["kind"] == "regression" and c["source_trace_id"].startswith("tr-timeout")
    ]
    assert timeout_cases

    case = timeout_cases[0]
    checks = {chk["type"]: chk for chk in case["expected"]["checks"]}
    # Empty failure output (timeout): any non-empty output must pass
    assert "not_contains" not in checks
    assert checks["regex"]["pattern"] == r"\S"


def test_no_tool_loop_only_on_loop_failures(tmp_path):
    cases = _generate_cases(tmp_path)
    for case in cases:
        check_types = [chk["type"] for chk in case["expected"]["checks"]]
        if "no_tool_loop" in check_types:
            assert case["kind"] == "regression"
            assert case["source_trace_id"].startswith("tr-loop"), case["id"]


def test_golden_cases_unchanged(tmp_path):
    cases = _generate_cases(tmp_path)
    order_goldens = [
        c for c in cases if c["kind"] == "golden" and "order" in c["input"].lower()
    ]
    assert order_goldens

    case = order_goldens[0]
    checks = {chk["type"]: chk for chk in case["expected"]["checks"]}
    assert "contains_any" in checks
    assert checks["tool_sequence"]["tools"] == ["order_lookup"]
    assert case["reference_output"]
