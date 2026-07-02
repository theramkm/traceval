from pathlib import Path

from traceval.analyze import run_analysis
from traceval.analyze.report import render_report
from traceval.ingest import ingest_file
from traceval.store import TraceStore

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"


def test_report_xss_escaping(tmp_path):
    # Hostile string to test XSS safety
    hostile_input = "<script>alert('XSS')</script> & hostile & \"quotes\""

    # 1. Create a dummy summary
    summary = {
        "total_traces": 1,
        "outcomes": {"success": 1},
        "clusters": [
            {
                "id": "c_xss",
                "name": hostile_input,
                "tool_signature": "hostile_tool",
                "trace_count": 1,
                "trace_ids": ["tr-xss"],
            }
        ],
    }

    coverage = {"c_xss": 0}
    report_html = tmp_path / "report.html"

    # Render report
    render_report(summary, coverage, report_html)

    # Read output and assert escaping
    html_content = report_html.read_text(encoding="utf-8")
    assert "<script>" not in html_content
    assert "&lt;script&gt;" in html_content
    assert "alert" in html_content


def test_coverage_and_uncovered_alerts(tmp_path):
    # Setup database with high traffic cluster and check that alerts are flagged
    db_path = tmp_path / "test.db"
    store = TraceStore(db_path)

    # 1. Ingest generic traces
    ingest_file(FIXTURES_DIR / "generic_traces.jsonl", store, format_name="generic")

    # Create an evals directory with a single case matching tr-001 (success cluster)
    evals_dir = tmp_path / "evals"
    evals_dir.mkdir()

    # tr-001 is success (R_DEFAULT_SUCCESS)
    # tr-002 is tool_error
    case1_file = evals_dir / "case_1.yaml"
    case1_file.write_text(
        """
cluster: c_abc_success
source_trace_id: tr-001
input: "Where is my order 12345?"
""",
        encoding="utf-8",
    )

    # Run analysis
    run_analysis(db_path, evals_dir=evals_dir, output_dir=tmp_path / "out")

    # Report html should exist
    assert (tmp_path / "out" / "report.html").exists()

    html_content = (tmp_path / "out" / "report.html").read_text(encoding="utf-8")

    # Check that there are alerts for uncovered clusters (e.g. loops or tool
    # errors which have 0 cases)
    assert "Coverage Gaps Detected" in html_content

    store.close()
