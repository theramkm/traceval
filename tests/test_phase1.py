import json
from pathlib import Path

from typer.testing import CliRunner

from traceval.cli import app
from traceval.ingest import detect_format, ingest_file
from traceval.model import LLMCall, Message, Outcome, Step, Trace
from traceval.store import TraceStore


def test_model_serialization():
    msg_in = Message(role="user", content="hello")
    msg_out = Message(role="assistant", content="hi")
    llm = LLMCall(
        span_id="span-1",
        model="gemini",
        input_messages=[msg_in],
        output_message=msg_out,
    )
    step = Step(index=0, kind="llm", llm=llm)
    trace = Trace(
        trace_id="tr-test",
        source="generic",
        started_at="2026-07-01T12:00:00Z",
        task_input="hello",
        steps=[step],
    )
    data = trace.model_dump_json()
    parsed = Trace.model_validate(json.loads(data))
    assert parsed.trace_id == "tr-test"
    assert len(parsed.steps) == 1
    assert parsed.steps[0].llm.span_id == "span-1"


def test_store_operations(tmp_path):
    db_path = tmp_path / "test.db"
    store = TraceStore(db_path)
    assert store.count_traces() == 0

    trace = Trace(
        trace_id="tr-1",
        source="generic",
        started_at="2026-07-01T12:00:00Z",
        task_input="hello",
        steps=[],
    )
    store.save_trace(trace)
    assert store.count_traces() == 1

    fetched = store.get_trace("tr-1")
    assert fetched is not None
    assert fetched.trace_id == "tr-1"

    traces = list(store.list_traces())
    assert len(traces) == 1
    assert traces[0].trace_id == "tr-1"

    # Save with outcome
    trace.outcome = Outcome(label="success", reason="worked", labeled_by="rule")
    store.save_trace(trace)
    fetched2 = store.get_trace("tr-1")
    assert fetched2.outcome is not None
    assert fetched2.outcome.label == "success"

    store.close()


def test_generic_adapter_corrupt_lines(tmp_path):
    db_path = tmp_path / "test.db"
    store = TraceStore(db_path)
    log_path = tmp_path / "ingest.log"

    # Write a temporary JSONL with one good line, one corrupt line, one good line
    test_jsonl = tmp_path / "test_traces.jsonl"
    trace1 = Trace(
        trace_id="tr-ok1",
        source="generic",
        started_at="2026-07-01T12:00:00Z",
        task_input="input1",
        steps=[],
    )
    trace2 = Trace(
        trace_id="tr-ok2",
        source="generic",
        started_at="2026-07-01T12:01:00Z",
        task_input="input2",
        steps=[],
    )
    with open(test_jsonl, "w", encoding="utf-8") as f:
        f.write(trace1.model_dump_json() + "\n")
        f.write("{this is not valid json}\n")
        f.write(trace2.model_dump_json() + "\n")

    ok_count, span_count, warn_count, log_file = ingest_file(
        test_jsonl, store, format_name="generic", log_path=log_path
    )
    assert ok_count == 2
    assert span_count == 0
    assert warn_count == 1
    assert log_file == log_path
    assert log_path.exists()

    log_content = log_path.read_text(encoding="utf-8")
    assert "failed to parse trace" in log_content

    assert store.count_traces() == 2
    store.close()


def test_detect_format(tmp_path):
    test_jsonl = tmp_path / "test_traces.jsonl"
    trace = Trace(
        trace_id="tr-detect",
        source="generic",
        started_at="2026-07-01T12:00:00Z",
        task_input="detect",
        steps=[],
    )
    test_jsonl.write_text(trace.model_dump_json() + "\n", encoding="utf-8")
    fmt = detect_format(test_jsonl)
    assert fmt == "generic"


def test_cli_ingest(tmp_path):
    fixture_path = (
        Path(__file__).parent.parent / "tests" / "fixtures" / "generic_traces.jsonl"
    )
    db_path = tmp_path / "cli_test.db"

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["ingest", str(fixture_path), "-o", str(db_path), "--format", "generic"],
    )
    assert result.exit_code == 0
    assert "Ingested 12 traces" in result.stdout

    store = TraceStore(db_path)
    assert store.count_traces() == 12
    store.close()
