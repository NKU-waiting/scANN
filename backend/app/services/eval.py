"""性能评测服务。

以 FlatIndex 精确检索结果为 ground truth，评测 ANN 索引的召回率与耗时。
"""
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
    """评测单个索引的召回率与耗时。

    Returns:
        {
            "index_type": str,
            "recall_at_k": float,   # 平均 recall@top_k
            "top_k": int,
            "n_queries": int,
            "avg_query_ms": float,  # 目标索引平均查询耗时
            "build_ms": float,      # 目标索引构建耗时
        }
    """
    n_queries = min(n_queries, dataset.n_cells)
    rng = np.random.default_rng(seed)
    query_ids = rng.choice(dataset.n_cells, size=n_queries, replace=False)
    queries = dataset.vectors[query_ids]  # (n_queries, dim)

    # Ground truth: FlatIndex
    flat = FlatIndex(dim=dataset.dim, metric=metric)
    flat.build(dataset.vectors)

    # fetch top_k+1 to exclude the query cell itself
    fetch = min(top_k + 1, dataset.n_cells)
    gt_ids, _ = flat.search(queries, fetch)  # (n_queries, fetch)

    # Build target index
    t0 = time.perf_counter()
    target = create_index(index_type, dataset.dim, metric)
    target.build(dataset.vectors)
    build_ms = (time.perf_counter() - t0) * 1000

    # Query target index
    query_times = []
    recalls = []
    for i, qid in enumerate(query_ids):
        q = queries[i]
        t0 = time.perf_counter()
        pred_ids, _ = target.search(q, fetch)
        query_times.append((time.perf_counter() - t0) * 1000)

        # Remove the query cell itself from both result sets, keep top_k
        gt_set = {idx for idx in gt_ids[i].tolist() if idx != int(qid)}
        pred_set = {idx for idx in pred_ids[0].tolist() if idx != int(qid)}
        gt_set = set(list(gt_set)[:top_k])
        pred_set = set(list(pred_set)[:top_k])

        hit = len(gt_set & pred_set)
        recalls.append(hit / top_k if top_k > 0 else 1.0)

    return {
        "index_type": index_type,
        "recall_at_k": round(float(np.mean(recalls)), 4),
        "top_k": top_k,
        "n_queries": n_queries,
        "avg_query_ms": round(float(np.mean(query_times)), 3),
        "build_ms": round(build_ms, 2),
    }
