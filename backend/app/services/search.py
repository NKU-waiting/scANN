"""检索服务（核心模块）。

维护「当前数据集 + 当前索引」的进程内单例，提供：
- build_index(): 构建/重建索引
- search_by_cell() / search_by_vector(): Top-K 相似细胞检索，支持条件过滤

进程启动时自动用演示数据初始化，保证最小流程开箱即用。
"""
from __future__ import annotations

import time

import numpy as np

from app.core.config import Config
from app.services.data_loader import CellDataset, make_demo_dataset
from app.services.index import create_index


class SearchService:
    def __init__(self):
        self.dataset: CellDataset | None = None
        self.index = None
        self.index_type: str = Config.DEFAULT_INDEX_TYPE
        self.metric: str = Config.DEFAULT_METRIC

    # ---- 初始化 / 数据 ----
    def ensure_initialized(self) -> None:
        if self.dataset is None:
            self.load_demo()

    def load_demo(self) -> None:
        self.dataset = make_demo_dataset(Config.DEMO_N_CELLS, Config.DEMO_DIM)
        self.build_index(self.index_type, self.metric)

    def set_dataset(self, dataset: CellDataset) -> dict:
        self.dataset = dataset
        return self.build_index(self.index_type, self.metric)

    # ---- 索引 ----
    def build_index(self, index_type: str | None = None, metric: str | None = None) -> dict:
        self.ensure_dataset()
        self.index_type = index_type or self.index_type
        self.metric = metric or self.metric

        t0 = time.perf_counter()
        self.index = create_index(self.index_type, self.dataset.dim, self.metric)
        self.index.build(self.dataset.vectors)
        build_ms = (time.perf_counter() - t0) * 1000
        return {**self.status(), "build_ms": round(build_ms, 2)}

    def status(self) -> dict:
        return {
            "dataset": self.dataset.name if self.dataset else None,
            "n_cells": self.dataset.n_cells if self.dataset else 0,
            "dim": self.dataset.dim if self.dataset else 0,
            "index": self.index.name if self.index else None,
            "index_type": self.index_type,
            "metric": self.metric,
            "metadata_fields": sorted(self.dataset.obs.keys()) if self.dataset else [],
            "ready": self.index is not None,
        }

    # ---- 检索 ----
    def search_by_cell(self, cell_id: int, top_k: int, cell_type: str | None = None) -> dict:
        self.ensure_ready()
        if not (0 <= cell_id < self.dataset.n_cells):
            raise ValueError(f"cell_id 越界: {cell_id}")
        query = self.dataset.vectors[cell_id]
        return self._run(query, top_k, exclude={cell_id}, cell_type=cell_type)

    def search_by_vector(self, vector: list[float], top_k: int, cell_type: str | None = None) -> dict:
        self.ensure_ready()
        query = np.asarray(vector, dtype=np.float32)
        if query.shape[-1] != self.dataset.dim:
            raise ValueError(f"向量维度应为 {self.dataset.dim}，收到 {query.shape[-1]}")
        return self._run(query, top_k, exclude=set(), cell_type=cell_type)

    def _run(self, query: np.ndarray, top_k: int, exclude: set[int],
             cell_type: str | None) -> dict:
        # 条件检索时在全库范围内取候选，过滤后再截断到 top_k；
        # 否则仅多取少量候选以排除自身。
        fetch = self.dataset.n_cells if cell_type else top_k + len(exclude) + 1
        t0 = time.perf_counter()
        idx, dist = self.index.search(query, fetch)
        query_ms = (time.perf_counter() - t0) * 1000

        types = self.dataset.obs.get("cell_type")
        results = []
        for i, d in zip(idx[0].tolist(), dist[0].tolist()):
            if i < 0 or i in exclude:
                continue
            if cell_type and types and types[i] != cell_type:
                continue
            results.append({
                "cell_id": i,
                "cell_name": self.dataset.cell_ids[i],
                "distance": round(float(d), 4),
                "cell_type": types[i] if types else None,
            })
            if len(results) >= top_k:
                break

        return {
            "results": results,
            "query_ms": round(query_ms, 3),
            "index": self.index.name,
            "returned": len(results),
        }

    # ---- 守卫 ----
    def ensure_dataset(self) -> None:
        if self.dataset is None:
            raise RuntimeError("尚未加载数据集")

    def ensure_ready(self) -> None:
        self.ensure_initialized()
        if self.index is None:
            self.build_index()


# 进程内单例
search_service = SearchService()
