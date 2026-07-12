"""Reproducible ANN evaluation against an exact Flat ground truth."""

from __future__ import annotations

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
