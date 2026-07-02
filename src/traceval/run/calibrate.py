"""Judge calibration: compare LLM-judge verdicts against human labels.

An LLM judge's scores are only trustworthy if they agree with human
expertise. This module extracts judge-scored results from a run report,
samples them deterministically, and computes judge-vs-human agreement
(overall and per cluster), flagging buckets that fall below a threshold.
"""

import random
from typing import Any


def extract_judged_results(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull results that carry a judge check plus the fields calibrate needs.

    Reports written before 0.2.0 lack ``input``/``output`` fields; those
    results are skipped so callers can degrade gracefully.
    """
    judged: list[dict[str, Any]] = []
    for res in report.get("results", []):
        scores = res.get("scores", {})
        judge_key = next((k for k in scores if k.startswith("judge_")), None)
        if judge_key is None:
            continue
        if "input" not in res or "output" not in res:
            continue
        judge_score = scores[judge_key]
        judged.append(
            {
                "case_id": res["case_id"],
                "cluster": res.get("cluster", ""),
                "input": res["input"],
                "output": res["output"],
                "judge_passed": bool(judge_score["passed"]),
                "judge_score": judge_score.get("score"),
                "judge_detail": judge_score.get("detail", ""),
            }
        )
    return judged


def sample_judged(
    judged: list[dict[str, Any]],
    n: int,
    seed: int = 0,
) -> list[dict[str, Any]]:
    """Deterministic sample of up to n results, ordered by case id."""
    if n >= len(judged):
        picked = list(judged)
    else:
        picked = random.Random(seed).sample(judged, n)
    return sorted(picked, key=lambda r: str(r["case_id"]))


def compute_agreement(
    labeled: list[dict[str, Any]],
    min_agreement: float = 0.8,
) -> dict[str, Any]:
    """Judge-vs-human agreement over items labeled with ``human_passed``.

    false_pass (judge passed, human failed) is the dangerous direction: the
    judge is waving bad outputs through.
    """
    total = len(labeled)
    agree = sum(1 for r in labeled if r["judge_passed"] == r["human_passed"])
    false_pass = sum(1 for r in labeled if r["judge_passed"] and not r["human_passed"])
    false_fail = sum(1 for r in labeled if not r["judge_passed"] and r["human_passed"])

    per_cluster: dict[str, dict[str, Any]] = {}
    for r in labeled:
        stats = per_cluster.setdefault(str(r["cluster"]), {"total": 0, "agree": 0})
        stats["total"] += 1
        if r["judge_passed"] == r["human_passed"]:
            stats["agree"] += 1
    for stats in per_cluster.values():
        stats["agreement"] = stats["agree"] / stats["total"]

    flagged = sorted(
        cluster
        for cluster, stats in per_cluster.items()
        if stats["agreement"] < min_agreement
    )

    return {
        "total": total,
        "agreement": agree / total if total else None,
        "false_pass": false_pass,
        "false_fail": false_fail,
        "per_cluster": per_cluster,
        "min_agreement": min_agreement,
        "flagged_clusters": flagged,
    }
