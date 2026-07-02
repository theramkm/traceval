import random
from pathlib import Path

from traceval.ingest import detect_format, ingest_file
from traceval.store import TraceStore

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"


def test_detect_formats():
    otel_path = FIXTURES_DIR / "otel_spans.jsonl"
    lf_path = FIXTURES_DIR / "langfuse_export.jsonl"
    ls_path = FIXTURES_DIR / "langsmith_runs.jsonl"

    assert detect_format(otel_path) == "otel"
    assert detect_format(lf_path) == "langfuse"
    assert detect_format(ls_path) == "langsmith"


def test_otel_ingest(tmp_path):
    db_path = tmp_path / "otel.db"
    log_path = tmp_path / "otel_ingest.log"
    store = TraceStore(db_path)

    ok_count, _span_count, warn_count, log_file = ingest_file(
        FIXTURES_DIR / "otel_spans.jsonl",
        store,
        format_name="otel",
        log_path=log_path,
    )

    # 5 traces are defined in our otel_spans.jsonl + 1 invalid line
    assert ok_count == 5
    assert warn_count == 1
    assert log_file == log_path

    traces = list(store.list_traces())
    assert len(traces) == 5

    # Check trace 1 detail: otel-001 has 1 llm step and 1 tool step
    t1 = next(t for t in traces if t.trace_id == "otel-001")
    assert len(t1.steps) == 2
    assert t1.steps[0].kind == "llm"
    assert t1.steps[0].llm.model == "gemini-2.5"
    assert len(t1.steps[0].llm.input_messages) == 1
    assert t1.steps[0].llm.output_message.content == "Let me lookup order 12345."

    assert t1.steps[1].kind == "tool"
    assert t1.steps[1].tool.name == "order_lookup"
    assert t1.steps[1].tool.arguments_json == '{"order_id": "12345"}'

    # Check tool error parsing
    t2 = next(t for t in traces if t.trace_id == "otel-002")
    assert len(t2.steps) == 1
    assert t2.steps[0].kind == "tool"
    assert t2.steps[0].tool.error == "Connection timed out"

    store.close()


def test_langfuse_ingest(tmp_path):
    db_path = tmp_path / "lf.db"
    log_path = tmp_path / "lf_ingest.log"
    store = TraceStore(db_path)

    ok_count, _span_count, warn_count, _log_file = ingest_file(
        FIXTURES_DIR / "langfuse_export.jsonl",
        store,
        format_name="langfuse",
        log_path=log_path,
    )

    # 5 traces + 1 invalid line
    assert ok_count == 5
    assert warn_count == 1

    traces = list(store.list_traces())
    assert len(traces) == 5

    t1 = next(t for t in traces if t.trace_id == "lf-001")
    assert len(t1.steps) == 2
    assert t1.steps[0].kind == "llm"
    assert t1.steps[1].kind == "tool"

    store.close()


def test_langsmith_ingest(tmp_path):
    db_path = tmp_path / "ls.db"
    log_path = tmp_path / "ls_ingest.log"
    store = TraceStore(db_path)

    ok_count, _span_count, warn_count, _log_file = ingest_file(
        FIXTURES_DIR / "langsmith_runs.jsonl",
        store,
        format_name="langsmith",
        log_path=log_path,
    )

    # 5 traces + 1 invalid line
    assert ok_count == 5
    assert warn_count == 1

    traces = list(store.list_traces())
    assert len(traces) == 5

    t1 = next(t for t in traces if t.trace_id == "ls-trace-1")
    assert len(t1.steps) == 2
    assert t1.steps[0].kind == "llm"
    assert t1.steps[1].kind == "tool"

    store.close()


def test_robustness_on_shuffled_inputs(tmp_path):
    # Tests that feeding shuffled spans to the OTel parser does not crash it
    otel_path = FIXTURES_DIR / "otel_spans.jsonl"
    lines = otel_path.read_text(encoding="utf-8").splitlines()

    # Shuffle the non-corrupt lines
    clean_lines = [line for line in lines if "INVALID_LINE" not in line]
    random.seed(42)
    random.shuffle(clean_lines)

    shuffled_file = tmp_path / "otel_shuffled.jsonl"
    shuffled_file.write_text("\n".join(clean_lines) + "\n", encoding="utf-8")

    db_path = tmp_path / "otel_shuffled.db"
    store = TraceStore(db_path)

    ok_count, _span_count, warn_count, _log_file = ingest_file(
        shuffled_file,
        store,
        format_name="otel",
    )
    # Reconstructs all 5 traces
    assert ok_count == 5
    assert warn_count == 0
    store.close()
