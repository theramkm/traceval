import json
from pathlib import Path

from typer.testing import CliRunner

from traceval.analyze.coverage import compute_coverage
from traceval.cli import app
from traceval.compile import generate_evals
from traceval.ingest import ingest_file
from traceval.run.judge import (
    FakeJudge,
    get_judge_call_count,
    reset_judge_call_count,
    resolve_judge,
)
from traceval.run.scorers import (
    score_contains_any,
    score_exact,
    score_json_schema,
    score_judge,
    score_no_tool_loop,
    score_not_contains,
    score_regex,
    score_tool_sequence,
)
from traceval.run.target import CallableTarget, HttpTarget, resolve_target
from traceval.store import TraceStore

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"


# Dummy target callable for tests
def dummy_agent_fn(input_text: str) -> dict:
    if "12345" in input_text:
        return {
            "output": "Your order 12345 is in transit.",
            "tool_calls": ["order_lookup"],
        }
    elif "stripe" in input_text.lower() or "refund" in input_text.lower():
        return {
            "output": "Failed processing refund.",
            "tool_calls": ["stripe_lookup"],
        }
    return {"output": "Hello there!", "tool_calls": []}


def test_targets_resolution():
    t_http = resolve_target("http://localhost:8080/agent")
    assert isinstance(t_http, HttpTarget)
    assert t_http.url == "http://localhost:8080/agent"

    t_call = resolve_target("tests.test_phase6:dummy_agent_fn")
    assert isinstance(t_call, CallableTarget)
    res = t_call.invoke("Where is order 12345?")
    assert res["output"] == "Your order 12345 is in transit."
    assert res["tool_calls"] == ["order_lookup"]


def test_scorers():
    # 1. Exact
    assert score_exact("hello", "hello").passed
    assert not score_exact("hello", "world").passed

    # 2. Contains any
    assert score_contains_any("My order is shipped", ["shipped", "arrived"]).passed
    assert not score_contains_any("My order is pending", ["shipped", "arrived"]).passed

    # 3. Regex
    assert score_regex("Order 123", r"\d+").passed
    assert not score_regex("Order abc", r"\d+").passed

    # 4. JSON Schema
    schema = {
        "type": "object",
        "properties": {"status": {"type": "string"}},
        "required": ["status"],
    }
    assert score_json_schema('{"status": "ok"}', schema).passed
    assert not score_json_schema('{"status": 123}', schema).passed
    assert not score_json_schema("invalid json", schema).passed

    # 5. Tool Sequence
    # subset
    assert score_tool_sequence(["a", "b", "c"], ["a", "c"], mode="subset").passed
    assert not score_tool_sequence(["a", "b"], ["a", "c"], mode="subset").passed
    # order
    assert score_tool_sequence(["a", "b", "c"], ["a", "c"], mode="order").passed
    assert not score_tool_sequence(["c", "b", "a"], ["a", "c"], mode="order").passed

    # 6. Judge
    judge = FakeJudge()
    assert score_judge(
        judge, "rubric", "input", "output with input keyword", "reference"
    ).passed

    # 7. Not contains (inverted): fails when any forbidden value appears
    assert score_not_contains("Refund processed via Stripe.", ["error", "loop"]).passed
    assert not score_not_contains("Error: service unavailable", ["error"]).passed
    assert score_not_contains("anything", []).passed

    # 8. No tool loop: fails on >= max_repeats consecutive identical calls
    assert not score_no_tool_loop(["a", "a", "a"], max_repeats=3).passed
    assert score_no_tool_loop(["a", "b", "a", "a"], max_repeats=3).passed
    assert score_no_tool_loop(["a", "b", "c"], max_repeats=3).passed
    assert score_no_tool_loop([], max_repeats=3).passed
    assert not score_no_tool_loop(["x", "a", "a", "a", "a", "y"], max_repeats=3).passed


def test_fake_judge_neutral_passes_default_threshold():
    reset_judge_call_count()
    judge = FakeJudge()

    # No >=4-char word overlap between output and input/reference: FakeJudge
    # returns its neutral score, which must clear the generated default
    # min_score (0.7) so offline runs are gated by deterministic checks only.
    res = score_judge(judge, "rubric", "timeout hang task", "Hello! Nice day.", None)
    assert res.passed
    assert res.score >= 0.7


def test_judge_budget_cap():
    reset_judge_call_count()
    judge = FakeJudge()

    # Trigger 200 calls
    for _ in range(200):
        judge.score("rubric", "input", "output", "reference")

    assert get_judge_call_count() == 200

    # 201st call should return score 0.0 with budget exceeded message
    res = judge.score("rubric", "input", "output", "reference")
    assert res.score == 0.0
    assert "budget exceeded" in res.reasons[0].lower()


def test_e2e_runner_execution(tmp_path):
    db_path = tmp_path / "test.db"
    store = TraceStore(db_path)
    ingest_file(FIXTURES_DIR / "generic_traces.jsonl", store, format_name="generic")
    store.close()

    evals_dir = tmp_path / "evals"
    generate_evals(db_path, evals_dir, include_failures=True)

    # Run the CLI suite against the dummy target
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "run",
            str(evals_dir),
            "--target",
            "tests.test_phase6:dummy_agent_fn",
            "--judge",
            "fake",
        ],
    )
    # Pytest finished successfully (either code 0 or exit_code of tests)
    assert result.exit_code in [0, 1]

    # Verify run report is written inside the evals dir
    runs_dir = evals_dir / "runs"
    assert runs_dir.exists()

    report_files = list(runs_dir.glob("*.json"))
    assert len(report_files) > 0

    # Load and assert content structure
    with open(report_files[0], encoding="utf-8") as f:
        report = json.load(f)
    assert "summary" in report
    assert "results" in report
    assert report["summary"]["total"] > 0


def test_openai_compat_judge(monkeypatch):
    reset_judge_call_count()

    # Mock httpx.post for OpenAICompatJudge
    def mock_post(url, headers=None, json=None, timeout=None):
        class MockResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": '{"score": 0.9, "reasons": ["looks good"]}'
                            }
                        }
                    ]
                }

        return MockResponse()

    import httpx

    monkeypatch.setattr(httpx, "post", mock_post)

    judge = resolve_judge("gpt-4o:https://api.openai.com/v1")
    # inject mock key
    # mypy complains about attribute modification since Judge is a Protocol.
    # We can cast or set directly
    judge.api_key = "fake_key"  # type: ignore[attr-defined]

    res = judge.score("rubric", "input", "output", "reference")
    assert res.score == 0.9
    assert res.reasons == ["looks good"]


def test_http_target_mock(monkeypatch):
    # Mock httpx.post for HttpTarget
    def mock_post(url, json=None, timeout=None):
        class MockResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "output": "http response",
                    "tool_calls": [{"name": "web_search"}],
                }

        return MockResponse()

    import httpx

    monkeypatch.setattr(httpx, "post", mock_post)

    target = resolve_target("http://localhost:8080/agent")
    res = target.invoke("hello")
    assert res["output"] == "http response"
    assert res["tool_calls"] == ["web_search"]


def test_coverage_scenarios(tmp_path):
    from traceval.analyze.cluster import Cluster
    from traceval.model import Trace

    clusters = [
        Cluster(
            id="c_1",
            name="cluster one",
            trace_ids=["tr-1"],
            tool_signature="",
            top_terms=["hello"],
        ),
        Cluster(
            id="c_2",
            name="cluster two",
            trace_ids=["tr-2"],
            tool_signature="",
            top_terms=["world"],
        ),
    ]

    traces = [
        Trace(
            trace_id="tr-1",
            source="generic",
            started_at="2026-07-01T12:00:00Z",
            task_input="hello input",
            steps=[],
        ),
        Trace(
            trace_id="tr-2",
            source="generic",
            started_at="2026-07-01T12:00:00Z",
            task_input="world input",
            steps=[],
        ),
    ]

    evals_dir = tmp_path / "evals"
    evals_dir.mkdir()

    # Case A: explicit cluster field
    case_a = evals_dir / "case_a.yaml"
    case_a.write_text("cluster: c_1\ninput: hello", encoding="utf-8")

    # Case B: trace ID lookup
    case_b = evals_dir / "case_b.yaml"
    case_b.write_text("source_trace_id: tr-2\ninput: world", encoding="utf-8")

    # Case C: similarity fallback
    case_c = evals_dir / "case_c.yaml"
    case_c.write_text("input: hello input text", encoding="utf-8")

    res = compute_coverage(clusters, evals_dir, traces)
    assert res["c_1"] == 2
    assert res["c_2"] == 1
