from pathlib import Path

import yaml

from traceval.analyze.cluster import Cluster, get_ngrams, tokenize
from traceval.model import Trace


def compute_coverage(
    clusters: list[Cluster],
    evals_dir: Path | None,
    traces: list[Trace],
) -> dict[str, int]:
    coverage: dict[str, int] = {c.id: 0 for c in clusters}
    if not evals_dir or not evals_dir.exists():
        return coverage

    # 1. Parse all eval files (*.yaml) in evals_dir recursively
    eval_cases = []
    for p in evals_dir.rglob("*.yaml"):
        # Skip potential metadata yaml like traceval.yaml
        if p.name == "traceval.yaml":
            continue
        try:
            with open(p, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict) and "input" in data:
                    eval_cases.append(data)
        except Exception:
            pass

    # 2. For each eval case, map to a cluster
    traces_by_id = {t.trace_id: t for t in traces}
    cluster_by_id = {c.id: c for c in clusters}

    for case in eval_cases:
        mapped_cluster_id = None

        # Scenario A: case has a explicit 'cluster' field
        case_cluster = case.get("cluster")
        if case_cluster and case_cluster in cluster_by_id:
            mapped_cluster_id = case_cluster

        # Scenario B: look up the source trace and find which cluster contains it
        elif "source_trace_id" in case:
            tid = case["source_trace_id"]
            for c in clusters:
                if tid in c.trace_ids:
                    mapped_cluster_id = c.id
                    break

        # Scenario C: fallback to input similarity match
        if not mapped_cluster_id:
            case_input = case.get("input", "")
            case_ngrams = get_ngrams(tokenize(case_input))
            best_sim = -1.0
            best_cid = None

            for c in clusters:
                # Compare similarity with each trace in the cluster
                for tid in c.trace_ids:
                    t = traces_by_id.get(tid)
                    if not t:
                        continue
                    t_ngrams = get_ngrams(tokenize(t.task_input))
                    if not case_ngrams or not t_ngrams:
                        sim = 0.0
                    else:
                        union_len = len(case_ngrams.union(t_ngrams))
                        sim = (
                            len(case_ngrams.intersection(t_ngrams)) / union_len
                            if union_len > 0
                            else 0.0
                        )
                    if sim > best_sim:
                        best_sim = sim
                        best_cid = c.id
            if best_sim >= 0.35:
                mapped_cluster_id = best_cid

        if mapped_cluster_id:
            coverage[mapped_cluster_id] += 1

    return coverage
