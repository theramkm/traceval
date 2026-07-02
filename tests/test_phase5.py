import re
import subprocess
import sys
from pathlib import Path

from traceval.compile import generate_evals
from traceval.ingest import ingest_file
from traceval.store import TraceStore

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"


# Dummy hook for custom PII test
def custom_pii_hook(text: str) -> str:
    return re.sub(r"slow", "[REDACTED_SLOW]", text, flags=re.IGNORECASE)


def test_determinism_and_redaction(tmp_path):
    db_path = tmp_path / "test.db"
    store = TraceStore(db_path)
    ingest_file(FIXTURES_DIR / "generic_traces.jsonl", store, format_name="generic")
    store.close()

    evals_dir1 = tmp_path / "evals1"
    evals_dir2 = tmp_path / "evals2"

    # Generate twice
    generate_evals(db_path, evals_dir1, include_failures=True)
    generate_evals(db_path, evals_dir2, include_failures=True)

    # 1. Assert conftest and test_generated exist
    assert (evals_dir1 / "conftest.py").exists()
    assert (evals_dir1 / "test_generated.py").exists()

    # 2. Assert byte-identical YAML files
    yaml_files1 = sorted(evals_dir1.rglob("*.yaml"))
    yaml_files2 = sorted(evals_dir2.rglob("*.yaml"))
    assert len(yaml_files1) == len(yaml_files2)
    assert len(yaml_files1) > 0

    for f1, f2 in zip(yaml_files1, yaml_files2, strict=False):
        assert f1.read_bytes() == f2.read_bytes()

    # 3. Assert PII was redacted from tr-008.
    # tr-008 input contains card "1111-2222-3333-4444" and email "test@domain.com"
    # Find YAML file for trace 8
    tr_008_yaml = None
    for yf in yaml_files1:
        if "tr-008" in yf.read_text(encoding="utf-8"):
            tr_008_yaml = yf
            break

    assert tr_008_yaml is not None
    yaml_content = tr_008_yaml.read_text(encoding="utf-8")
    assert "1111-2222-3333-4444" not in yaml_content
    assert "test@domain.com" not in yaml_content
    assert "[REDACTED_CARD]" in yaml_content
    assert "[REDACTED_EMAIL]" in yaml_content


def test_custom_redact_hook(tmp_path):
    db_path = tmp_path / "test.db"
    store = TraceStore(db_path)
    ingest_file(FIXTURES_DIR / "generic_traces.jsonl", store, format_name="generic")
    store.close()

    evals_dir = tmp_path / "evals_hook"

    # We specify hook as "tests.test_phase5:custom_pii_hook"
    generate_evals(
        db_path,
        evals_dir,
        include_failures=True,
        redact_hook_str="tests.test_phase5:custom_pii_hook",
    )

    # Check that word "slow" was redacted from tr-011 (Slow command execution)
    tr_011_yaml = None
    for yf in evals_dir.rglob("*.yaml"):
        if "tr-011" in yf.read_text(encoding="utf-8"):
            tr_011_yaml = yf
            break

    assert tr_011_yaml is not None
    yaml_content = tr_011_yaml.read_text(encoding="utf-8")
    assert "[REDACTED_SLOW]" in yaml_content
    assert "Slow" not in yaml_content  # "Slow" -> "[REDACTED_SLOW]"
    # Let's assert slow is not present
    assert "slow" not in yaml_content.replace("[REDACTED_SLOW]", "").lower()


def test_pytest_collection(tmp_path):
    db_path = tmp_path / "test.db"
    store = TraceStore(db_path)
    ingest_file(FIXTURES_DIR / "generic_traces.jsonl", store, format_name="generic")
    store.close()

    evals_dir = tmp_path / "evals_pytest"
    generate_evals(db_path, evals_dir, include_failures=True)

    # Run pytest --collect-only on the generated directory
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(evals_dir),
        "--collect-only",
        "--target",
        "http://localhost:8000",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    assert result.returncode == 0
    # Should successfully collect cases (we had 12 traces)
    assert "collected" in result.stdout
    assert "errors" not in result.stderr.lower()
