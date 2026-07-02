import hashlib
import math
import re
from collections import Counter
from typing import Protocol

from pydantic import BaseModel

from traceval.model import Trace


class Cluster(BaseModel):
    id: str
    name: str
    trace_ids: list[str]
    tool_signature: str
    top_terms: list[str]


class Clusterer(Protocol):
    def cluster(self, traces: list[Trace]) -> list[Cluster]: ...


# Standard English stopwords
STOPWORDS: set[str] = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "is",
    "are",
    "was",
    "were",
    "to",
    "for",
    "in",
    "of",
    "on",
    "at",
    "by",
    "with",
    "this",
    "that",
    "these",
    "those",
    "i",
    "you",
    "he",
    "she",
    "it",
    "we",
    "they",
    "my",
    "your",
    "his",
    "her",
    "its",
    "our",
    "their",
    "me",
    "him",
    "us",
    "them",
    "what",
    "where",
    "how",
    "why",
    "please",
    "can",
    "get",
    "show",
    "find",
}


def tokenize(text: str) -> list[str]:
    # Lowercase and strip non-alphanumeric
    text = text.lower()
    words = re.findall(r"\b[a-z0-9_]+\b", text)
    return [w for w in words if w not in STOPWORDS]


NUM_TOKEN = "<num>"


def normalize_numeric_tokens(tokens: list[str]) -> list[str]:
    """Collapse digit-only tokens (ids, amounts) to a single placeholder.

    Applied only where similarity shingles are built: "Where is order 57978?"
    and "Where is order 12345?" express the same intent and must not seed
    separate clusters. NOT applied in generic tokenize(), where literal
    tokens matter (e.g. contains_any check inference).
    """
    return [NUM_TOKEN if t.isdigit() else t for t in tokens]


def get_ngrams(tokens: list[str], max_n: int = 3) -> set[tuple[str, ...]]:
    ngrams: set[tuple[str, ...]] = set()
    n_tokens = len(tokens)
    for n in range(1, min(max_n + 1, n_tokens + 1)):
        for i in range(n_tokens - n + 1):
            ngrams.add(tuple(tokens[i : i + n]))
    return ngrams


def get_tool_signature(trace: Trace) -> str:
    tool_names = []
    for step in trace.steps:
        if step.kind == "tool" and step.tool:
            tool_names.append(step.tool.name)
    return ">".join(tool_names) if tool_names else ""


class JaccardClusterer:
    def __init__(self, jaccard_threshold: float = 0.35) -> None:
        self.jaccard_threshold = jaccard_threshold

    def cluster(self, traces: list[Trace]) -> list[Cluster]:
        if not traces:
            return []

        # 1. Group traces by exact tool signature
        traces_by_sig: dict[str, list[Trace]] = {}
        for trace in traces:
            sig = get_tool_signature(trace)
            traces_by_sig.setdefault(sig, []).append(trace)

        raw_clusters: list[tuple[str, list[Trace]]] = []

        # 2. Within each signature group, apply greedy Jaccard
        # clustering on task_input ngrams
        for sig, sig_traces in traces_by_sig.items():
            # Keep trace list sorted by trace_id to ensure determinism
            sorted_traces = sorted(sig_traces, key=lambda t: t.trace_id)

            sig_clusters: list[list[Trace]] = []
            cluster_ngrams: list[set[tuple[str, ...]]] = []

            for trace in sorted_traces:
                tokens = normalize_numeric_tokens(tokenize(trace.task_input))
                ngrams = get_ngrams(tokens)

                matched_idx = -1
                for idx, seed_ngrams in enumerate(cluster_ngrams):
                    if not ngrams or not seed_ngrams:
                        jaccard = 0.0
                    else:
                        intersection = len(ngrams.intersection(seed_ngrams))
                        union = len(ngrams.union(seed_ngrams))
                        jaccard = intersection / union if union > 0 else 0.0

                    if jaccard >= self.jaccard_threshold:
                        matched_idx = idx
                        break

                if matched_idx != -1:
                    sig_clusters[matched_idx].append(trace)
                else:
                    sig_clusters.append([trace])
                    cluster_ngrams.append(ngrams)

            for group in sig_clusters:
                raw_clusters.append((sig, group))

        # 3. Calculate TF-IDF of terms per cluster to name them
        # Term counts per cluster
        cluster_term_docs: list[Counter[str]] = []
        doc_frequencies: Counter[str] = Counter()
        all_terms: set[str] = set()

        for _sig, group in raw_clusters:
            terms: list[str] = []
            for t in group:
                # Numeric tokens are cluster-fragmentation noise, not names
                terms.extend(tok for tok in tokenize(t.task_input) if not tok.isdigit())
            counter = Counter(terms)
            cluster_term_docs.append(counter)
            for term in counter:
                doc_frequencies[term] += 1
                all_terms.add(term)

        num_clusters = len(raw_clusters)
        idfs: dict[str, float] = {}
        for term in all_terms:
            # Standard smooth IDF formula
            idfs[term] = math.log((num_clusters + 1) / (doc_frequencies[term] + 1)) + 1

        clusters: list[Cluster] = []
        for c_idx, (sig, group) in enumerate(raw_clusters):
            # Compute TF-IDF for each term in this cluster
            term_scores = {}
            counter = cluster_term_docs[c_idx]
            for term, count in counter.items():
                tf = count  # raw term frequency in the cluster docs
                term_scores[term] = tf * idfs[term]

            # Sort terms by TF-IDF score
            sorted_terms = sorted(
                term_scores.keys(), key=lambda term: term_scores[term], reverse=True
            )
            top_terms = sorted_terms[:3]

            # Reconstruct signature string for title (replace '>' with ' -> ')
            formatted_sig = sig.replace(">", " -> ") if sig else ""

            # Outcome suffix (optional, if we want to differentiate failure clusters)
            outcomes = [t.outcome.label if t.outcome else "unknown" for t in group]
            outcome_counter = Counter(outcomes)
            dominant_outcome = outcome_counter.most_common(1)[0][0]

            # Build name
            name_parts = []
            if top_terms:
                name_parts.append(" ".join(top_terms))
            if formatted_sig:
                name_parts.append(formatted_sig)
            if dominant_outcome != "success":
                name_parts.append(f"({dominant_outcome})")

            name = " -> ".join(name_parts) if name_parts else "unclassified"

            # Stable content hash ID based on sorted list of trace_ids in the cluster
            sorted_ids = sorted(t.trace_id for t in group)
            joined_ids = ",".join(sorted_ids)
            content_hash = hashlib.sha256(joined_ids.encode("utf-8")).hexdigest()[:8]
            cluster_id = f"c_{content_hash}"

            clusters.append(
                Cluster(
                    id=cluster_id,
                    name=name,
                    trace_ids=sorted_ids,
                    tool_signature=sig,
                    top_terms=top_terms,
                )
            )

        # Sort clusters by id for deterministic outputs
        return sorted(clusters, key=lambda c: c.id)
