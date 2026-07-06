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

    # 6 traces are defined in our otel_spans.jsonl + 1 invalid line
    assert ok_count == 6
    assert warn_count == 1
    assert log_file == log_path

    traces = list(store.list_traces())
    assert len(traces) == 6

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

    # 6 traces + 1 invalid line
    assert ok_count == 6
    assert warn_count == 1

    traces = list(store.list_traces())
    assert len(traces) == 6

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
    # Reconstructs all 6 traces
    assert ok_count == 6
    assert warn_count == 0
    store.close()


def test_real_tool_names_detected(tmp_path):
    # Tool detection must not depend on the demo agent's tool vocabulary:
    # the create_ticket spans in both fixtures classify as tools via the
    # documented signals (Langfuse input/output heuristic; OTel gen_ai
    # semantic-convention attributes), never a name list.
    for fixture, fmt, trace_id in [
        ("langfuse_export.jsonl", "langfuse", "lf-006"),
        ("otel_spans.jsonl", "otel", "otel-006"),
    ]:
        store = TraceStore(tmp_path / f"{fmt}.db")
        ingest_file(FIXTURES_DIR / fixture, store, format_name=fmt)
        traces = list(store.list_traces())
        store.close()

        trace = next(t for t in traces if t.trace_id == trace_id)
        tool_steps = [s for s in trace.steps if s.kind == "tool"]
        assert len(tool_steps) == 1, f"{fmt}: create_ticket span not detected"
        assert tool_steps[0].tool.name == "create_ticket"


def test_tool_span_globs_override(tmp_path):
    # User globs replace the built-in Langfuse heuristic: with a glob that
    # matches nothing, the create_ticket SPAN (no metadata.tool) must NOT
    # classify as a tool; with a matching glob it must.
    store = TraceStore(tmp_path / "none.db")
    ingest_file(
        FIXTURES_DIR / "langfuse_export.jsonl",
        store,
        format_name="langfuse",
        tool_span_globs=["nothing_matches_*"],
    )
    trace = next(t for t in store.list_traces() if t.trace_id == "lf-006")
    store.close()
    assert all(s.kind != "tool" for s in trace.steps)

    store = TraceStore(tmp_path / "match.db")
    ingest_file(
        FIXTURES_DIR / "langfuse_export.jsonl",
        store,
        format_name="langfuse",
        tool_span_globs=["create_*"],
    )
    trace = next(t for t in store.list_traces() if t.trace_id == "lf-006")
    store.close()
    assert [s.kind for s in trace.steps] == ["tool"]
    assert trace.steps[0].tool.name == "create_ticket"


def test_langfuse_observe_root_and_ended_at(tmp_path):
    # Real modern-@observe shape: a root SPAN (the entry function) plus child
    # observations, and trace-level `latency`. Regression for two gaps found on
    # a real Langfuse dump: the root span must NOT be a tool, and ended_at must
    # be computed from latency (else R_TIMEOUT misfires on every trace).
    import json

    trace = {
        "id": "lf-observe-1",
        "timestamp": "2026-07-06T12:00:00Z",
        "latency": 3.5,
        "input": "look up penicillin",
        "output": "Penicillin is an antibiotic.",
        "observations": [
            {
                "id": "root", "type": "SPAN", "name": "run_agent",
                "parentObservationId": None,
                "startTime": "2026-07-06T12:00:00Z", "endTime": "2026-07-06T12:00:03Z",
                "input": "look up penicillin", "output": "Penicillin is an antibiotic.",
            },
            {
                "id": "gen", "type": "GENERATION", "name": "llm",
                "parentObservationId": "root",
                "startTime": "2026-07-06T12:00:01Z", "endTime": "2026-07-06T12:00:02Z",
                "input": [{"role": "user", "content": "look up penicillin"}],
                "output": {"role": "assistant", "content": "calling tool"},
            },
            {
                "id": "tool", "type": "SPAN", "name": "wikipedia_search",
                "parentObservationId": "root",
                "startTime": "2026-07-06T12:00:02Z", "endTime": "2026-07-06T12:00:03Z",
                "input": {"query": "penicillin"}, "output": "antibiotic",
            },
        ],
    }
    p = tmp_path / "observe.jsonl"
    p.write_text(json.dumps(trace) + "\n", encoding="utf-8")

    store = TraceStore(tmp_path / "observe.db")
    ingest_file(p, store, format_name="langfuse")
    t = next(t for t in store.list_traces() if t.trace_id == "lf-observe-1")
    store.close()

    # ended_at computed from latency (start 12:00:00 + 3.5s)
    assert t.ended_at is not None
    # root run_agent span is not a tool; the real tool child is
    tool_names = [s.tool.name for s in t.steps if s.kind == "tool" and s.tool]
    assert "run_agent" not in tool_names
    assert "wikipedia_search" in tool_names


def test_langfuse_observe_export_shape(tmp_path):
    # Real modern-@observe Langfuse export shape, captured as a permanent
    # contract from Phase D first contact (camelCase, flat observations list
    # including the root SPAN, trace-level timestamp + latency).
    store = TraceStore(tmp_path / "obs.db")
    ingest_file(
        FIXTURES_DIR / "langfuse_observe_export.jsonl", store, format_name="langfuse"
    )
    traces = {t.trace_id: t for t in store.list_traces()}
    store.close()

    full = traces["lf-obs-full"]
    # ended_at is computed from `latency`, in SECONDS. Verified against the real
    # export in Phase D: latency / observed-span == 1.0 (see phase-d/FINDINGS.md).
    # 12:00:00 + 3.5s.
    assert full.ended_at is not None
    assert (full.ended_at - full.started_at).total_seconds() == 3.5
    # The root run_agent SPAN is the trace envelope, not a tool; the real tool
    # child is classified as a tool, and the GENERATION as an llm step.
    tool_names = [s.tool.name for s in full.steps if s.kind == "tool" and s.tool]
    assert "run_agent" not in tool_names
    assert "wikipedia_search" in tool_names
    assert any(s.kind == "llm" for s in full.steps)

    # Single-observation edge: the agent failed before any child, so the root is
    # not referenced as a parent. Name-match still identifies it, so it is not a
    # tool step.
    single = traces["lf-obs-single"]
    assert all(s.kind != "tool" for s in single.steps)


def test_langfuse_latency_absent_keeps_ended_at_none(tmp_path):
    # Old flat exports carry no `latency`; ended_at must stay None so R_TIMEOUT
    # behavior is unchanged, and the root-skip must not fire without parent
    # structure or a name match (backward compatibility).
    import json

    trace = {
        "id": "lf-nolat",
        "name": "agent_run",
        "timestamp": "2026-07-06T12:00:00Z",
        "input": "hi",
        "output": "hello",
        "observations": [
            {
                "id": "g", "type": "GENERATION", "name": "llm_call",
                "startTime": "2026-07-06T12:00:00Z", "endTime": "2026-07-06T12:00:01Z",
                "input": [{"role": "user", "content": "hi"}],
                "output": {"role": "assistant", "content": "hello"},
            }
        ],
    }
    p = tmp_path / "nolat.jsonl"
    p.write_text(json.dumps(trace) + "\n", encoding="utf-8")
    store = TraceStore(tmp_path / "nolat.db")
    ingest_file(p, store, format_name="langfuse")
    t = next(iter(store.list_traces()))
    store.close()
    assert t.ended_at is None
