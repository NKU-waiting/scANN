"""Thread-safe retrieval service for the active dataset and index."""
from __future__ import annotations

import threading
import time

import numpy as np
from flask import current_app, has_app_context

from app.core.config import Config
from app.services.data_loader import CellDataset, make_demo_dataset
from app.services.index import FlatIndex, create_index


class SearchService:
    """Own the active dataset/index pair and replace it atomically."""

    def __init__(self):
        self.dataset: CellDataset | None = None
        self.index = None
        self.index_type: str = Config.DEFAULT_INDEX_TYPE
        self.metric: str = Config.DEFAULT_METRIC
        self.index_record_id: int | None = None
        self._lock = threading.RLock()

    # ---- initialization / datasets ----
    def ensure_initialized(self) -> None:
        with self._lock:
            if self.dataset is None:
                self.load_demo()

    def load_demo(self) -> dict:
        dataset = make_demo_dataset(
            self._config("DEMO_N_CELLS"),
            self._config("DEMO_DIM"),
        )
        return self.set_dataset(dataset, index_type="flat", metric="l2")

    def set_dataset(
        self,
        dataset: CellDataset,
        index_type: str | None = None,
        metric: str | None = None,
    ) -> dict:
        """Build first, then atomically publish a new dataset/index pair."""
        if not isinstance(dataset, CellDataset):
            raise ValueError("dataset 类型无效")
        with self._lock:
            candidate_type = (index_type or self.index_type).strip().lower()
            candidate_metric = (metric or self.metric).strip().lower()
            candidate = create_index(candidate_type, dataset.dim, candidate_metric)
            t0 = time.perf_counter()
            candidate.build(dataset.vectors)
            build_ms = (time.perf_counter() - t0) * 1000
            self.dataset = dataset
            self.index = candidate
            self.index_type = candidate_type
            self.metric = candidate_metric
            self.index_record_id = None
            return {**self._status_unlocked(), "build_ms": round(build_ms, 2)}

    def snapshot(self) -> tuple:
        """Capture references needed to roll back a cross-resource transaction."""
        with self._lock:
            return (
                self.dataset,
                self.index,
                self.index_type,
                self.metric,
                self.index_record_id,
            )

    def restore(self, snapshot: tuple) -> None:
        """Restore a state captured by :meth:`snapshot` without rebuilding it."""
        with self._lock:
            (
                self.dataset,
                self.index,
                self.index_type,
                self.metric,
                self.index_record_id,
            ) = snapshot

    def reset(self) -> None:
        """Clear process-local state; primarily useful for isolated application tests."""
        with self._lock:
            self.dataset = None
            self.index = None
            self.index_type = Config.DEFAULT_INDEX_TYPE
            self.metric = Config.DEFAULT_METRIC
            self.index_record_id = None

    # ---- indexes ----
    def build_index(self, index_type: str | None = None, metric: str | None = None) -> dict:
        """Build a candidate index and publish it only after a successful build."""
        with self._lock:
            self.ensure_dataset()
            candidate_type = (index_type or self.index_type).lower()
            candidate_metric = (metric or self.metric).lower()
            candidate = create_index(candidate_type, self.dataset.dim, candidate_metric)

            t0 = time.perf_counter()
            candidate.build(self.dataset.vectors)
            build_ms = (time.perf_counter() - t0) * 1000

            self.index = candidate
            self.index_type = candidate_type
            self.metric = candidate_metric
            self.index_record_id = None
            return {**self._status_unlocked(), "build_ms": round(build_ms, 2)}

    def status(self) -> dict:
        with self._lock:
            return self._status_unlocked()

    def _status_unlocked(self) -> dict:
        return {
            "dataset": self.dataset.name if self.dataset else None,
            "dataset_id": self.dataset.record_id if self.dataset else None,
            "dataset_fingerprint": self.dataset.fingerprint if self.dataset else None,
            "n_cells": self.dataset.n_cells if self.dataset else 0,
            "dim": self.dataset.dim if self.dataset else 0,
            "index": self.index.name if self.index else None,
            "index_type": self.index_type,
            "index_record_id": self.index_record_id,
            "persisted": self.index_record_id is not None,
            "metric": self.metric,
            "metadata_fields": sorted(self.dataset.obs.keys()) if self.dataset else [],
            "ready": self.index is not None,
        }

    def install_index(
        self,
        index,
        index_type: str,
        metric: str,
        record_id: int,
        dataset_fingerprint: str,
    ) -> dict:
        """Atomically install a validated persisted index for the active dataset."""
        with self._lock:
            self.ensure_dataset()
            if self.dataset.fingerprint != dataset_fingerprint:
                raise ValueError("索引与当前数据集不匹配")
            if index.dim != self.dataset.dim or index.n_items != self.dataset.n_cells:
                raise ValueError("索引规模或维度与当前数据集不匹配")
            self.index = index
            self.index_type = index_type
            self.metric = metric
            self.index_record_id = record_id
            return self._status_unlocked()

    def mark_index_persisted(self, record_id: int) -> dict:
        with self._lock:
            self.ensure_ready()
            self.index_record_id = record_id
            return self._status_unlocked()

    def locked_state(self):
        """Expose the active immutable references while holding the service lock."""
        return _LockedSearchState(self)

    # ---- retrieval ----
    def search_by_cell(
        self,
        cell_id: int,
        top_k: int,
        cell_type: str | None = None,
    ) -> dict:
        with self._lock:
            self.ensure_ready()
            self._validate_top_k(top_k)
            if not isinstance(cell_id, int) or isinstance(cell_id, bool):
                raise ValueError("cell_id 必须是整数")
            if not 0 <= cell_id < self.dataset.n_cells:
                raise ValueError(f"cell_id 越界: {cell_id}")
            query = self.dataset.vectors[cell_id]
            return self._run(query, top_k, exclude={cell_id}, cell_type=cell_type)

    def search_by_vector(
        self,
        vector: list[float],
        top_k: int,
        cell_type: str | None = None,
    ) -> dict:
        with self._lock:
            self.ensure_ready()
            self._validate_top_k(top_k)
            try:
                query = np.asarray(vector, dtype=np.float32)
            except (TypeError, ValueError) as exc:
                raise ValueError("vector 必须是一维有限数值数组") from exc
            if query.ndim != 1:
                raise ValueError("vector 必须是一维有限数值数组")
            if query.shape[0] != self.dataset.dim:
                raise ValueError(f"向量维度应为 {self.dataset.dim}，收到 {query.shape[0]}")
            if not np.isfinite(query).all():
                raise ValueError("vector 必须是一维有限数值数组")
            return self._run(query, top_k, exclude=set(), cell_type=cell_type)

    def _run(
        self,
        query: np.ndarray,
        top_k: int,
        exclude: set[int],
        cell_type: str | None,
    ) -> dict:
        t0 = time.perf_counter()
        if cell_type is not None:
            ids, values = self._filtered_exact_search(query, top_k, exclude, cell_type)
            filter_strategy = "exact_subset"
        else:
            fetch = min(self.dataset.n_cells, top_k + len(exclude))
            raw_ids, raw_values = self.index.search(query, max(1, fetch))
            pairs = [
                (idx, value)
                for idx, value in zip(raw_ids[0].tolist(), raw_values[0].tolist())
                if idx >= 0 and idx not in exclude
            ][:top_k]
            ids = [idx for idx, _ in pairs]
            values = [value for _, value in pairs]
            filter_strategy = None
        query_ms = (time.perf_counter() - t0) * 1000

        types = self.dataset.obs.get("cell_type")
        results = [
            {
                "cell_id": idx,
                "cell_name": self.dataset.cell_ids[idx],
                "distance": round(float(value), 6),
                "cell_type": types[idx] if types else None,
            }
            for idx, value in zip(ids, values)
        ]
        score_kind = {
            "l2": "squared_l2_distance",
            "cosine": "cosine_distance",
            "ip": "inner_product",
        }[self.metric]
        return {
            "results": results,
            "query_ms": round(query_ms, 3),
            "index": self.index.name,
            "index_type": self.index_type,
            "metric": self.metric,
            "dataset_id": self.dataset.record_id,
            "dataset": self.dataset.name,
            "dataset_fingerprint": self.dataset.fingerprint,
            "score_kind": score_kind,
            "higher_is_better": self.metric == "ip",
            "filter_strategy": filter_strategy,
            "returned": len(results),
        }

    def _filtered_exact_search(
        self,
        query: np.ndarray,
        top_k: int,
        exclude: set[int],
        cell_type: str,
    ) -> tuple[list[int], list[float]]:
        types = self.dataset.obs.get("cell_type")
        if types is None:
            raise ValueError("当前数据集不包含 cell_type 元数据")
        eligible = [
            idx
            for idx, value in enumerate(types)
            if value == cell_type and idx not in exclude
        ]
        if not eligible:
            return [], []

        subset = FlatIndex(self.dataset.dim, self.metric)
        subset.build(self.dataset.vectors[eligible])
        local_ids, values = subset.search(query, min(top_k, len(eligible)))
        ids = [eligible[local_id] for local_id in local_ids[0].tolist()]
        return ids, values[0].tolist()

    # ---- guards ----
    def _validate_top_k(self, top_k: int) -> None:
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top_k 必须是正整数")
        max_top_k = self._config("MAX_TOP_K")
        if top_k > max_top_k:
            raise ValueError(f"top_k 不能超过 {max_top_k}")

    @staticmethod
    def _config(name: str):
        if has_app_context():
            return current_app.config[name]
        return getattr(Config, name)

    def ensure_dataset(self) -> None:
        if self.dataset is None:
            raise RuntimeError("尚未加载数据集")

    def ensure_ready(self) -> None:
        self.ensure_initialized()
        if self.index is None:
            self.build_index()


search_service = SearchService()


class _LockedSearchState:
    def __init__(self, service: SearchService):
        self.service = service

    def __enter__(self):
        self.service._lock.acquire()
        self.service.ensure_ready()
        return (
            self.service.dataset,
            self.service.index,
            self.service.index_type,
            self.service.metric,
        )

    def __exit__(self, exc_type, exc_value, traceback):
        self.service._lock.release()
