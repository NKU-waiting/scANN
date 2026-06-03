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
        return faiss.METRIC_INNER_PRODUCT if self.metric == "ip" else faiss.METRIC_L2

    def build(self, vectors: np.ndarray) -> None:
        import faiss

        vectors = self._as_2d_f32(vectors)
        d, m = self.dim, self._metric_flag()

        if self.variant == "hnsw":
            index = faiss.IndexHNSWFlat(d, 32, m)
        elif self.variant == "ivf":
            quantizer = faiss.IndexFlat(d, m)
            nlist = max(1, int(np.sqrt(vectors.shape[0])))
            index = faiss.IndexIVFFlat(quantizer, d, nlist, m)
            index.train(vectors)
        elif self.variant == "pq":
            m_sub = 8 if d % 8 == 0 else 1     # 子量化器数量需整除维度
            index = faiss.IndexPQ(d, m_sub, 8)
            index.train(vectors)
        else:  # flat
            index = faiss.IndexFlat(d, m)

        index.add(vectors)
        self._index = index
        self.n_items = index.ntotal

    def search(self, queries: np.ndarray, top_k: int) -> tuple[np.ndarray, np.ndarray]:
        q = self._as_2d_f32(queries)
        distances, indices = self._index.search(q, min(top_k, self.n_items))
        return indices, distances

    def save(self, path: str) -> None:
        import faiss
        faiss.write_index(self._index, path)

    def load(self, path: str) -> None:
        import faiss
        self._index = faiss.read_index(path)
        self.n_items = self._index.ntotal
