"""FAISS 索引实现（ANN 核心）。

支持 variant：
- "faiss"/"flat" : IndexFlat（精确，作对照基线）
- "ivf"          : IndexIVFFlat（先聚类再局部搜索）
- "hnsw"         : IndexHNSWFlat（图结构，高召回 + 高效率）
- "pq"           : IndexPQ（乘积量化，省内存）

后续可在 build() 中暴露 nlist / nprobe / M / efSearch 等调参入口。
"""
from __future__ import annotations

import numpy as np

from .base import BaseIndex


class FaissIndex(BaseIndex):
    def __init__(self, dim: int, metric: str = "l2", variant: str = "faiss"):
        super().__init__(dim, metric)
        self.variant = variant if variant != "faiss" else "flat"
        self._index = None

    @property
    def name(self) -> str:
        return f"faiss-{self.variant}({self.metric})"

    def _metric_flag(self):
        import faiss
        return (
            faiss.METRIC_INNER_PRODUCT
            if self.metric in ("ip", "cosine")
            else faiss.METRIC_L2
        )

    def build(self, vectors: np.ndarray) -> None:
        import faiss

        vectors = self._prepare(vectors)
        d, m = self.dim, self._metric_flag()

        if self.variant == "hnsw":
            index = faiss.IndexHNSWFlat(d, 32, m)
            index.hnsw.efConstruction = 80
            index.hnsw.efSearch = 64
        elif self.variant == "ivf":
            quantizer = faiss.IndexFlat(d, m)
            nlist = max(1, int(np.sqrt(vectors.shape[0])))
            index = faiss.IndexIVFFlat(quantizer, d, nlist, m)
            index.train(vectors)
            index.nprobe = min(nlist, max(1, int(np.sqrt(nlist))))
        elif self.variant == "pq":
            divisors = [
                candidate
                for candidate in range(1, min(8, d) + 1)
                if d % candidate == 0
            ]
            m_sub = max(divisors)
            # FAISS clustering is most stable with roughly 39 training rows per centroid.
            max_centroids = max(2, vectors.shape[0] // 39)
            nbits = min(8, max(1, int(np.floor(np.log2(max_centroids)))))
            index = faiss.IndexPQ(d, m_sub, nbits, m)
            index.train(vectors)
        else:  # flat
            index = faiss.IndexFlat(d, m)

        index.add(vectors)
        self._index = index
        self.n_items = index.ntotal

    def search(self, queries: np.ndarray, top_k: int) -> tuple[np.ndarray, np.ndarray]:
        if self._index is None or self.n_items < 1:
            raise RuntimeError("索引尚未构建或加载")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top_k 必须是正整数")
        q = self._prepare(queries)
        distances, indices = self._index.search(q, min(top_k, self.n_items))
        if self.metric == "cosine":
            distances = np.clip(1.0 - distances, 0.0, 2.0)
        return indices, distances

    def save(self, path: str) -> None:
        import faiss
        faiss.write_index(self._index, path)

    def load(self, path: str) -> None:
        import faiss
        self._index = faiss.read_index(path)
        self.n_items = self._index.ntotal
