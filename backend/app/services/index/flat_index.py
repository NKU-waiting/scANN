"""Flat 精确检索（numpy 暴力）。

作为基线与 FAISS 不可用时的回退实现，无第三方依赖，保证最小流程始终可跑通。
"""
from __future__ import annotations

import numpy as np

from .base import BaseIndex


class FlatIndex(BaseIndex):
    @property
    def name(self) -> str:
        return f"flat({self.metric})"

    def build(self, vectors: np.ndarray) -> None:
        self._vectors = self._prepare(vectors)
        self.n_items = self._vectors.shape[0]

    def search(self, queries: np.ndarray, top_k: int) -> tuple[np.ndarray, np.ndarray]:
        if not hasattr(self, "_vectors") or self.n_items < 1:
            raise RuntimeError("索引尚未构建或加载")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top_k 必须是正整数")
        q = self._prepare(queries)
        top_k = min(top_k, self.n_items)

        if self.metric in ("ip", "cosine"):
            sims = q @ self._vectors.T
            idx = np.argpartition(-sims, top_k - 1, axis=1)[:, :top_k]
            order = np.argsort(-np.take_along_axis(sims, idx, axis=1), axis=1)
            idx = np.take_along_axis(idx, order, axis=1)
            values = np.take_along_axis(sims, idx, axis=1)
            if self.metric == "cosine":
                values = np.clip(1.0 - values, 0.0, 2.0)
            dist = values
            return idx, dist

        # 默认 L2 平方距离
        dists = (
            (q ** 2).sum(axis=1, keepdims=True)
            - 2 * q @ self._vectors.T
            + (self._vectors ** 2).sum(axis=1)
        )
        np.maximum(dists, 0.0, out=dists)
        idx = np.argpartition(dists, top_k - 1, axis=1)[:, :top_k]
        order = np.argsort(np.take_along_axis(dists, idx, axis=1), axis=1)
        idx = np.take_along_axis(idx, order, axis=1)
        dist = np.take_along_axis(dists, idx, axis=1)
        return idx, dist

    def save(self, path: str) -> None:
        np.save(path, self._vectors)

    def load(self, path: str) -> None:
        source = path if path.endswith(".npy") else path + ".npy"
        try:
            vectors = np.load(source, allow_pickle=False)
        except (OSError, ValueError) as exc:
            raise ValueError("无法读取 Flat 索引文件") from exc
        self._vectors = self._prepare(vectors)
        self.n_items = self._vectors.shape[0]
