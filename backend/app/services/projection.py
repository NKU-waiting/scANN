"""Cached deterministic 2D UMAP/PCA projections for result visualization."""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np

from app.services.search import search_service


@dataclass
class ProjectionCacheEntry:
    ids: np.ndarray
    coordinates: np.ndarray
    method: str
    transformer: object


class ProjectionService:
    def __init__(self, max_cache_entries: int = 8):
        self._cache: OrderedDict[tuple, ProjectionCacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._max_cache_entries = max_cache_entries

    def project(
        self,
        max_points: int,
        include_ids: list[int] | None = None,
        method: str = "umap",
    ) -> dict:
        search_service.ensure_initialized()
        dataset = search_service.snapshot()[0]
        if not dataset.fingerprint:
            raise ValueError("当前数据集缺少稳定指纹")
        include_ids = list(dict.fromkeys(include_ids or []))
        if any(not 0 <= index < dataset.n_cells for index in include_ids):
            raise ValueError("include_ids 包含越界细胞编号")

        key = (dataset.fingerprint, min(max_points, dataset.n_cells), method)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                entry = self._fit(dataset.vectors, key[1], method, dataset.fingerprint)
                self._cache[key] = entry
                while len(self._cache) > self._max_cache_entries:
                    self._cache.popitem(last=False)
            else:
                self._cache.move_to_end(key)

        present = set(entry.ids.tolist())
        extra_ids = [index for index in include_ids if index not in present]
        ids = entry.ids
        coordinates = entry.coordinates
        if extra_ids:
            extra_vectors = dataset.vectors[extra_ids]
            extra_coordinates = self._transform(entry, extra_vectors)
            ids = np.concatenate([ids, np.asarray(extra_ids, dtype=np.int64)])
            coordinates = np.vstack([coordinates, extra_coordinates])

        cell_types = dataset.obs.get("cell_type")
        points = [
            {
                "cell_id": int(cell_id),
                "cell_name": dataset.cell_ids[int(cell_id)],
                "cell_type": cell_types[int(cell_id)] if cell_types else None,
                "x": round(float(coordinate[0]), 6),
                "y": round(float(coordinate[1]), 6),
            }
            for cell_id, coordinate in zip(ids.tolist(), coordinates.tolist())
        ]
        return {
            "dataset": dataset.name,
            "dataset_id": dataset.record_id,
            "dataset_fingerprint": dataset.fingerprint,
            "method": entry.method,
            "n_cells": dataset.n_cells,
            "sampled": len(entry.ids),
            "returned": len(points),
            "points": points,
        }

    def _fit(
        self,
        vectors: np.ndarray,
        max_points: int,
        method: str,
        fingerprint: str,
    ) -> ProjectionCacheEntry:
        if vectors.shape[0] <= max_points:
            ids = np.arange(vectors.shape[0], dtype=np.int64)
        else:
            seed = int(fingerprint[:16], 16) % (2**32)
            rng = np.random.default_rng(seed)
            ids = np.sort(rng.choice(vectors.shape[0], size=max_points, replace=False))
        sampled = vectors[ids]

        if method == "umap" and len(ids) >= 4:
            import umap

            reducer = umap.UMAP(
                n_components=2,
                n_neighbors=min(15, len(ids) - 1),
                min_dist=0.1,
                metric="euclidean",
                random_state=42,
                transform_seed=42,
                n_jobs=1,
                low_memory=True,
            )
            coordinates = reducer.fit_transform(sampled).astype(np.float32)
            return ProjectionCacheEntry(ids, coordinates, "umap", reducer)

        mean = sampled.mean(axis=0, keepdims=True)
        centered = sampled - mean
        _, _, right = np.linalg.svd(centered, full_matrices=False)
        components = right[: min(2, right.shape[0])]
        coordinates = centered @ components.T
        if coordinates.shape[1] == 1:
            coordinates = np.column_stack([coordinates[:, 0], np.zeros(len(ids))])
        transformer = (mean, components)
        return ProjectionCacheEntry(
            ids,
            np.asarray(coordinates, dtype=np.float32),
            "pca",
            transformer,
        )

    @staticmethod
    def _transform(entry: ProjectionCacheEntry, vectors: np.ndarray) -> np.ndarray:
        if entry.method == "umap":
            return np.asarray(entry.transformer.transform(vectors), dtype=np.float32)
        mean, components = entry.transformer
        coordinates = (vectors - mean) @ components.T
        if coordinates.shape[1] == 1:
            coordinates = np.column_stack(
                [coordinates[:, 0], np.zeros(vectors.shape[0])]
            )
        return np.asarray(coordinates, dtype=np.float32)


projection_service = ProjectionService()
