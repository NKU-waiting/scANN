"""Reproducible ANN evaluation against an exact Flat ground truth."""

from __future__ import annotations

import hashlib
import time

import numpy as np

from app.services.data_loader import CellDataset
from app.services.index import FlatIndex, create_index


def evaluate_index(
    dataset: CellDataset,
    index_type: str,
    top_k: int = 10,
    n_queries: int = 100,
    metric: str = "l2",
    seed: int = 42,
) -> dict:
    """Evaluate one index with a well-defined effective K at dataset boundaries."""
    if dataset.n_cells < 2:
        raise ValueError("性能评测至少需要 2 个细胞")
    effective_k = min(top_k, dataset.n_cells - 1)
    actual_queries = min(n_queries, dataset.n_cells)
    rng = np.random.default_rng(seed)
    query_ids = rng.choice(dataset.n_cells, size=actual_queries, replace=False)
    queries = dataset.vectors[query_ids]

    flat = FlatIndex(dim=dataset.dim, metric=metric)
    flat.build(dataset.vectors)
    fetch = effective_k + 1
    ground_truth_ids, _ = flat.search(queries, fetch)

    t0 = time.perf_counter()
    target = create_index(index_type, dataset.dim, metric)
    target.build(dataset.vectors)
    build_ms = (time.perf_counter() - t0) * 1000
    index_bytes = target.size_bytes()

    query_times: list[float] = []
    recalls: list[float] = []
    for row, query_id in enumerate(query_ids):
        t0 = time.perf_counter()
        predicted_ids, _ = target.search(queries[row], fetch)
        query_times.append((time.perf_counter() - t0) * 1000)

        ground_truth = _neighbors_without_self(
            ground_truth_ids[row].tolist(), int(query_id), effective_k
        )
        predicted = _neighbors_without_self(predicted_ids[0].tolist(), int(query_id), effective_k)
        recalls.append(len(set(ground_truth) & set(predicted)) / len(ground_truth))

    return {
        "index_type": index_type,
        "recall_at_k": round(float(np.mean(recalls)), 4),
        "top_k": top_k,
        "effective_top_k": effective_k,
        "n_queries": actual_queries,
        "avg_query_ms": round(float(np.mean(query_times)), 3),
        "build_ms": round(build_ms, 2),
        "index_bytes": index_bytes,
        "index_fingerprint": target.fingerprint(),
        "bytes_per_vector": round(index_bytes / dataset.n_cells, 2),
        "parameters": target.parameters(),
        "query_seed": seed,
        "query_set_digest": hashlib.sha256(
            np.asarray(query_ids, dtype=np.dtype("<i8")).tobytes()
        ).hexdigest(),
    }


def pq_rerank_comparison(results: list[dict]) -> dict | None:
    """Build an auditable paired summary when PQ and its reranked variant are present."""
    by_type = {row["index_type"]: row for row in results}
    baseline = by_type.get("pq")
    improved = by_type.get("pq_rerank")
    if baseline is None or improved is None:
        return None
    if baseline["query_set_digest"] != improved["query_set_digest"]:
        raise RuntimeError("PQ 对照未使用相同查询集合")
    same_pq_index = baseline["index_fingerprint"] == improved["index_fingerprint"]
    return {
        "strategy": "pq_candidate_exact_rerank",
        "baseline_index_type": "pq",
        "improved_index_type": "pq_rerank",
        "same_query_set": True,
        "same_pq_index": same_pq_index,
        "query_set_digest": baseline["query_set_digest"],
        "recall_delta": round(improved["recall_at_k"] - baseline["recall_at_k"], 4),
        "avg_query_ms_delta": round(improved["avg_query_ms"] - baseline["avg_query_ms"], 3),
        "index_bytes_delta": improved["index_bytes"] - baseline["index_bytes"],
        "recall_non_decreasing": improved["recall_at_k"] + 1e-9 >= baseline["recall_at_k"],
        "guarantee": (
            "exact_rerank_of_superset_candidates" if same_pq_index else "measured_comparison_only"
        ),
    }


def _neighbors_without_self(ids: list[int], query_id: int, limit: int) -> list[int]:
    """Preserve ranking while removing invalid ids, self matches, and duplicates."""
    result: list[int] = []
    seen: set[int] = set()
    for candidate in ids:
        if candidate < 0 or candidate == query_id or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
        if len(result) == limit:
            break
    return result
