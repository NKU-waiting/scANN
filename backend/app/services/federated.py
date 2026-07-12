"""Atomic joint indexes and provenance-preserving cross-dataset retrieval."""

from __future__ import annotations

import hashlib
import threading
import time
from bisect import bisect_right
from dataclasses import dataclass

import numpy as np
from flask import current_app

from app.services.data_loader import CellDataset
from app.services.datasets import dataset_service
from app.services.index import FlatIndex, create_index
from app.services.search import search_service


@dataclass(frozen=True)
class DatasetSlice:
    """One source dataset's half-open range in a joint vector matrix."""

    dataset: CellDataset
    start: int
    stop: int

    def to_dict(self) -> dict:
        return {
            "dataset_id": self.dataset.record_id,
            "name": self.dataset.name,
            "fingerprint": self.dataset.fingerprint,
            "n_cells": self.dataset.n_cells,
            "dim": self.dataset.dim,
            "start": self.start,
            "stop": self.stop,
        }


class FederatedCollection:
    """Immutable joint vector snapshot with reversible source-cell identities."""

    def __init__(self, datasets: list[CellDataset], embedding_space: str):
        if not datasets:
            raise ValueError("向量集合至少需要 1 个数据集")
        dimensions = {dataset.dim for dataset in datasets}
        if len(dimensions) != 1:
            details = ", ".join(f"{dataset.name}={dataset.dim}" for dataset in datasets)
            raise ValueError(f"联合数据集向量维度不一致: {details}")

        self.embedding_space = embedding_space
        self.dim = datasets[0].dim
        self.slices: list[DatasetSlice] = []
        offset = 0
        for dataset in datasets:
            self.slices.append(DatasetSlice(dataset, offset, offset + dataset.n_cells))
            offset += dataset.n_cells
        self.n_cells = offset
        self.vectors = np.ascontiguousarray(
            np.concatenate([dataset.vectors for dataset in datasets], axis=0),
            dtype=np.float32,
        )
        self._starts = [entry.start for entry in self.slices]
        self._by_dataset_id = {entry.dataset.record_id: entry for entry in self.slices}
        self.fingerprint = self._fingerprint()

    @property
    def dataset_ids(self) -> list[int]:
        return [entry.dataset.record_id for entry in self.slices]

    def global_id(self, dataset_id: int, cell_id: int) -> int:
        entry = self._by_dataset_id.get(dataset_id)
        if entry is None:
            raise ValueError("查询数据集不属于当前联合索引")
        if not isinstance(cell_id, int) or isinstance(cell_id, bool):
            raise ValueError("cell_id 必须是整数")
        if not 0 <= cell_id < entry.dataset.n_cells:
            raise ValueError(f"cell_id 越界: {cell_id}")
        return entry.start + cell_id

    def resolve(self, global_id: int) -> tuple[DatasetSlice, int]:
        if not 0 <= global_id < self.n_cells:
            raise ValueError(f"联合细胞编号越界: {global_id}")
        entry = self.slices[bisect_right(self._starts, global_id) - 1]
        return entry, global_id - entry.start

    def _fingerprint(self) -> str:
        digest = hashlib.sha256()
        digest.update(b"scann-federated-collection-v1\0")
        _update_text(digest, self.embedding_space)
        for entry in self.slices:
            _update_text(digest, str(entry.dataset.record_id))
            _update_text(digest, entry.dataset.fingerprint or "")
        return digest.hexdigest()


class FederatedSearchService:
    """Own one published joint collection/index without disturbing the active dataset."""

    def __init__(self):
        self._lock = threading.RLock()
        self.collection: FederatedCollection | None = None
        self.index = None
        self.index_type: str | None = None
        self.metric: str | None = None

    def build(
        self,
        dataset_ids: list[int],
        embedding_space: str,
        index_type: str,
        metric: str,
    ) -> dict:
        if len(dataset_ids) < 2 or len(set(dataset_ids)) != len(dataset_ids):
            raise ValueError("联合索引需要至少 2 个不重复的数据集")
        if not isinstance(embedding_space, str) or not embedding_space.strip():
            raise ValueError("embedding_space 必须是非空字符串")
        embedding_space = embedding_space.strip()
        normalized_ids = sorted(dataset_ids)
        max_datasets = current_app.config["MAX_FEDERATED_DATASETS"]
        if len(normalized_ids) > max_datasets:
            raise ValueError(f"联合索引最多包含 {max_datasets} 个数据集")

        # Hold the lifecycle lock through publication so a source cannot be deleted
        # between file verification and installing the candidate collection.
        with search_service.lifecycle_lock():
            datasets = dataset_service.load_many(normalized_ids)
            max_cells = current_app.config["MAX_FEDERATED_CELLS"]
            if sum(dataset.n_cells for dataset in datasets) > max_cells:
                raise ValueError(f"联合索引细胞总数不能超过 {max_cells}")
            candidate_collection = FederatedCollection(datasets, embedding_space)
            candidate_index = create_index(index_type, candidate_collection.dim, metric)
            started = time.perf_counter()
            candidate_index.build(candidate_collection.vectors)
            build_ms = (time.perf_counter() - started) * 1000
            with self._lock:
                self.collection = candidate_collection
                self.index = candidate_index
                self.index_type = index_type
                self.metric = metric
                status = self._status_unlocked()
        return {**status, "build_ms": round(build_ms, 2)}

    def status(self) -> dict:
        with self._lock:
            return self._status_unlocked()

    def search_by_cell(
        self,
        dataset_id: int,
        cell_id: int,
        top_k: int,
        cell_type: str | None = None,
    ) -> dict:
        with self._lock:
            self._ensure_ready()
            global_id = self.collection.global_id(dataset_id, cell_id)
            entry, local_id = self.collection.resolve(global_id)
            query = self.collection.vectors[global_id]
            result = self._run(query, top_k, {global_id}, cell_type)
            result["query"] = {
                "dataset_id": entry.dataset.record_id,
                "dataset": entry.dataset.name,
                "cell_id": local_id,
                "cell_name": entry.dataset.cell_ids[local_id],
            }
            result["cross_dataset_returned"] = sum(
                row["dataset_id"] != dataset_id for row in result["results"]
            )
            return result

    def search_by_vector(
        self,
        vector: list[float],
        top_k: int,
        cell_type: str | None = None,
    ) -> dict:
        with self._lock:
            self._ensure_ready()
            try:
                query = np.asarray(vector, dtype=np.float32)
            except (TypeError, ValueError) as exc:
                raise ValueError("vector 必须是一维有限数值数组") from exc
            if query.ndim != 1 or query.shape[0] != self.collection.dim:
                raise ValueError(f"向量维度应为 {self.collection.dim}")
            if not np.isfinite(query).all():
                raise ValueError("vector 必须是一维有限数值数组")
            result = self._run(query, top_k, set(), cell_type)
            result["query"] = None
            result["cross_dataset_returned"] = None
            return result

    def invalidate_dataset(self, dataset_id: int) -> None:
        """Drop a published collection when any immutable source is deleted."""
        with self._lock:
            if self.collection and dataset_id in self.collection.dataset_ids:
                self.reset()

    def reset(self) -> None:
        with self._lock:
            self.collection = None
            self.index = None
            self.index_type = None
            self.metric = None

    def _run(
        self,
        query: np.ndarray,
        top_k: int,
        exclude: set[int],
        cell_type: str | None,
    ) -> dict:
        self._validate_top_k(top_k)
        started = time.perf_counter()
        if cell_type is None:
            fetch = min(self.collection.n_cells, top_k + len(exclude))
            raw_ids, raw_values = self.index.search(query, max(1, fetch))
            pairs = [
                (global_id, value)
                for global_id, value in zip(raw_ids[0].tolist(), raw_values[0].tolist())
                if global_id >= 0 and global_id not in exclude
            ][:top_k]
            filter_strategy = None
        else:
            pairs = self._filtered_exact_search(query, top_k, exclude, cell_type)
            filter_strategy = "exact_federated_subset"
        query_ms = (time.perf_counter() - started) * 1000

        results = []
        for global_id, value in pairs:
            entry, local_id = self.collection.resolve(global_id)
            types = entry.dataset.obs.get("cell_type")
            results.append(
                {
                    "global_cell_id": global_id,
                    "composite_id": f"{entry.dataset.record_id}:{local_id}",
                    "dataset_id": entry.dataset.record_id,
                    "dataset": entry.dataset.name,
                    "cell_id": local_id,
                    "cell_name": entry.dataset.cell_ids[local_id],
                    "cell_type": types[local_id] if types else None,
                    "distance": round(float(value), 6),
                }
            )
        score_kind = {
            "l2": "squared_l2_distance",
            "cosine": "cosine_distance",
            "ip": "inner_product",
        }[self.metric]
        return {
            "results": results,
            "returned": len(results),
            "query_ms": round(query_ms, 3),
            "index": self.index.name,
            "index_type": self.index_type,
            "metric": self.metric,
            "score_kind": score_kind,
            "higher_is_better": self.metric == "ip",
            "filter_strategy": filter_strategy,
            "collection_fingerprint": self.collection.fingerprint,
            "embedding_space": self.collection.embedding_space,
            "dataset_ids": self.collection.dataset_ids,
        }

    def _filtered_exact_search(
        self,
        query: np.ndarray,
        top_k: int,
        exclude: set[int],
        cell_type: str,
    ) -> list[tuple[int, float]]:
        eligible: list[int] = []
        has_cell_type = False
        for entry in self.collection.slices:
            types = entry.dataset.obs.get("cell_type")
            if types is None:
                continue
            has_cell_type = True
            eligible.extend(
                entry.start + local_id
                for local_id, value in enumerate(types)
                if value == cell_type and entry.start + local_id not in exclude
            )
        if not has_cell_type:
            raise ValueError("联合数据集不包含 cell_type 元数据")
        if not eligible:
            return []
        subset = FlatIndex(self.collection.dim, self.metric)
        subset.build(self.collection.vectors[eligible])
        local_ids, values = subset.search(query, min(top_k, len(eligible)))
        return [
            (eligible[local_id], value)
            for local_id, value in zip(local_ids[0].tolist(), values[0].tolist())
        ]

    def _status_unlocked(self) -> dict:
        if self.collection is None or self.index is None:
            return {
                "ready": False,
                "datasets": [],
                "dataset_ids": [],
                "n_cells": 0,
                "dim": 0,
                "embedding_space": None,
                "collection_fingerprint": None,
                "index": None,
                "index_type": None,
                "metric": None,
            }
        return {
            "ready": True,
            "datasets": [entry.to_dict() for entry in self.collection.slices],
            "dataset_ids": self.collection.dataset_ids,
            "n_cells": self.collection.n_cells,
            "dim": self.collection.dim,
            "embedding_space": self.collection.embedding_space,
            "collection_fingerprint": self.collection.fingerprint,
            "index": self.index.name,
            "index_type": self.index_type,
            "metric": self.metric,
            "parameters": self.index.parameters(),
            "compatibility": {
                "dimension_verified": True,
                "shared_space_asserted": True,
            },
        }

    def _validate_top_k(self, top_k: int) -> None:
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top_k 必须是正整数")
        max_top_k = current_app.config["MAX_TOP_K"]
        if top_k > max_top_k:
            raise ValueError(f"top_k 不能超过 {max_top_k}")

    def _ensure_ready(self) -> None:
        if self.collection is None or self.index is None:
            raise RuntimeError("尚未构建联合索引")


def _update_text(digest, value: str) -> None:
    encoded = value.encode("utf-8")
    digest.update(len(encoded).to_bytes(4, "big"))
    digest.update(encoded)


federated_search_service = FederatedSearchService()
