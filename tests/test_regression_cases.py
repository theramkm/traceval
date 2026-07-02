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


def _trace(trace_id, task_input, final_output, label):
    from traceval.model import Outcome, Trace

    return Trace(
        trace_id=trace_id,
        source="generic",
        started_at="2026-07-01T12:00:00Z",
        task_input=task_input,
        final_output=final_output,
        steps=[],
        outcome=Outcome(
            label=label, reason="test", rule_id="R_TEST", labeled_by="rule"
        ),
    )


def _cluster(cluster_id, traces):
    from traceval.analyze.cluster import Cluster

    return Cluster(
        id=cluster_id,
        name=cluster_id,
        trace_ids=[t.trace_id for t in traces],
        tool_signature="",
        top_terms=[],
    )


def test_signature_excludes_tokens_common_in_success_traces():
    from traceval.compile.cases import select_and_redact_cases

    # "service" appears in half the same-cluster successes (>= 10%), so it
    # must not be forbidden; "exploded" appears in none, so it must be.
    successes = [
        _trace(
            "s-1", "check account alpha", "Your service request is done.", "success"
        ),
        _trace(
            "s-2", "check account beta", "All finished, have a nice day.", "success"
        ),
    ]
    failure = _trace(
        "f-1", "check account gamma", "The service exploded badly.", "tool_error"
    )
    cluster = _cluster("c_test", [*successes, failure])

    cases = select_and_redact_cases(
        [cluster], [*successes, failure], include_failures=True
    )
    regression = next(c for c in cases if c["kind"] == "regression")
    not_contains = next(
        chk for chk in regression["expected"]["checks"] if chk["type"] == "not_contains"
    )
    assert "exploded" in not_contains["values"]
    assert "service" not in not_contains["values"]


def test_signature_falls_back_to_db_successes():
    from traceval.compile.cases import select_and_redact_cases

    # The failure cluster has no successes; distinctiveness must be computed
    # against all success traces in the db.
    db_success = _trace("s-1", "lookup thing", "The gateway responded fine.", "success")
    failure = _trace("f-1", "other request", "The gateway crashed hard.", "tool_error")
    cases = select_and_redact_cases(
        [_cluster("c_fail", [failure]), _cluster("c_ok", [db_success])],
        [db_success, failure],
        include_failures=True,
    )
    regression = next(c for c in cases if c["kind"] == "regression")
    not_contains = next(
        chk for chk in regression["expected"]["checks"] if chk["type"] == "not_contains"
    )
    # "gateway" is in the db success output -> excluded; "crashed" is not
    assert "crashed" in not_contains["values"]
    assert "gateway" not in not_contains["values"]


def test_no_not_contains_when_no_token_survives():
    from traceval.compile.cases import select_and_redact_cases

    # Every failure-output token is either echoed from the input, too short,
    # or common in success outputs -> the not_contains check must be omitted
    # entirely, never emitted with an empty/junk list.
    success = _trace("s-1", "ping", "Request completed without incident.", "success")
    failure = _trace(
        "f-1",
        "request completed incident",
        "Request completed incident. OK",
        "bad_output",
    )
    cases = select_and_redact_cases(
        [_cluster("c_f", [failure]), _cluster("c_s", [success])],
        [success, failure],
        include_failures=True,
    )
    regression = next(c for c in cases if c["kind"] == "regression")
    check_types = [chk["type"] for chk in regression["expected"]["checks"]]
    assert "not_contains" not in check_types
    assert "judge" in check_types
