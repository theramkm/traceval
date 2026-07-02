import json

from typer.testing import CliRunner

from traceval.cli import app
from traceval.run.calibrate import (
    compute_agreement,
    extract_judged_results,
    sample_judged,
)


def _result(case_id, cluster, judge_passed, judge_score=0.9, enriched=True):
    res = {
        "case_id": case_id,
        "cluster": cluster,
        "passed": judge_passed,
        "latency_ms": 1.0,
        "scores": {
            "contains_any_0": {"passed": True, "score": 1.0, "detail": "ok"},
            "judge_1": {
                "passed": judge_passed,
                "score": judge_score,
                "detail": "FakeJudge: overlap evaluated",
            },
        },
    }
    if enriched:
        res["input"] = f"input for {case_id}"
        res["output"] = f"output for {case_id}"
    return res


def test_extract_judged_results():
    report = {
        "results": [
            _result("c1__case_001", "c1", True),
            # No judge check at all
            {
                "case_id": "c1__case_002",
                "cluster": "c1",
                "passed": True,
                "scores": {"exact_0": {"passed": True, "score": 1.0, "detail": ""}},
                "input": "x",
                "output": "y",
            },
            # Pre-0.2.0 report item: judge check but no input/output
            _result("c2__case_003", "c2", False, enriched=False),
        ]
    }
    judged = extract_judged_results(report)
    assert [r["case_id"] for r in judged] == ["c1__case_001"]
    assert judged[0]["judge_passed"] is True
    assert judged[0]["judge_score"] == 0.9


def test_sample_judged_deterministic():
    judged = [{"case_id": f"case_{i:03d}", "cluster": "c"} for i in range(50)]
    s1 = sample_judged(judged, 10, seed=7)
    s2 = sample_judged(judged, 10, seed=7)
    assert s1 == s2
    assert len(s1) == 10
    # n larger than population returns everything
    assert len(sample_judged(judged, 100, seed=7)) == 50


def test_compute_agreement():
    labeled = [
        # c1: judge and human agree on both
        {"cluster": "c1", "judge_passed": True, "human_passed": True},
        {"cluster": "c1", "judge_passed": False, "human_passed": False},
        # c2: judge waves a bad output through (false pass), then agrees
        {"cluster": "c2", "judge_passed": True, "human_passed": False},
        {"cluster": "c2", "judge_passed": True, "human_passed": True},
        # c3: judge too harsh (false fail)
        {"cluster": "c3", "judge_passed": False, "human_passed": True},
    ]
    stats = compute_agreement(labeled, min_agreement=0.8)
    assert stats["total"] == 5
    assert stats["agreement"] == 3 / 5
    assert stats["false_pass"] == 1
    assert stats["false_fail"] == 1
    assert stats["per_cluster"]["c1"]["agreement"] == 1.0
    assert stats["per_cluster"]["c2"]["agreement"] == 0.5
    assert stats["flagged_clusters"] == ["c2", "c3"]

    assert compute_agreement([])["agreement"] is None


def test_calibrate_cli(tmp_path):
    report = {
        "summary": {"total": 2, "passed": 2, "failed": 0},
        "results": [
            _result("c1__case_001", "c1", True),
            _result("c2__case_002", "c2", True),
        ],
    }
    report_path = tmp_path / "run_test.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    out_path = tmp_path / "calibration.json"

    runner = CliRunner()
    # Human agrees with the judge on case 1, disagrees on case 2
    result = runner.invoke(
        app,
        ["calibrate", str(report_path), "--sample", "2", "-o", str(out_path)],
        input="y\nn\n",
    )
    assert result.exit_code == 0, result.output
    assert "Judge Calibration Summary" in result.output

    with open(out_path, encoding="utf-8") as f:
        calibration = json.load(f)
    assert calibration["stats"]["total"] == 2
    assert calibration["stats"]["agreement"] == 0.5
    assert calibration["stats"]["false_pass"] == 1
    assert calibration["stats"]["flagged_clusters"] == ["c2"]
    labels = {item["case_id"]: item["human_passed"] for item in calibration["labels"]}
    assert labels == {"c1__case_001": True, "c2__case_002": False}


def test_calibrate_cli_rejects_unenriched_report(tmp_path):
    # Pre-0.2.0 report: judge scores present but no input/output fields
    report = {
        "results": [_result("c1__case_001", "c1", True, enriched=False)],
    }
    report_path = tmp_path / "run_old.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["calibrate", str(report_path)])
    assert result.exit_code == 1
    assert "regenerate" in (result.output + str(result.stderr or "")).lower()
