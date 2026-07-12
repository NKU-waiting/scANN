"""FAISS 索引实现（ANN 核心）。

支持 variant：
- "faiss"/"flat" : IndexFlat（精确，作对照基线）
- "ivf"          : IndexIVFFlat（先聚类再局部搜索）
- "hnsw"         : IndexHNSWFlat（图结构，高召回 + 高效率）
- "pq"           : IndexPQ（乘积量化，省内存）
- "pq_rerank"    : IndexPQ 扩大候选集后按原始向量精确重排

后续可在 build() 中暴露 nlist / nprobe / M / efSearch 等调参入口。
"""

from __future__ import annotations

import hashlib

import numpy as np

from .base import BaseIndex


class FaissIndex(BaseIndex):
    RERANK_FACTOR = 4

    def __init__(self, dim: int, metric: str = "l2", variant: str = "faiss"):
        super().__init__(dim, metric)
        self.variant = variant if variant != "faiss" else "flat"
        self._index = None

    @property
    def name(self) -> str:
        return f"faiss-{self.variant}({self.metric})"

    def _metric_flag(self):
        import faiss

        return faiss.METRIC_INNER_PRODUCT if self.metric in ("ip", "cosine") else faiss.METRIC_L2

    def build(self, vectors: np.ndarray) -> None:
        import faiss

        source_vectors = self._as_2d_f32(vectors)
        vectors = self._prepare(source_vectors)
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
        elif self.variant in {"pq", "pq_rerank"}:
            divisors = [candidate for candidate in range(1, min(8, d) + 1) if d % candidate == 0]
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
        if self.variant == "pq_rerank":
            self._rerank_vectors = source_vectors

    def search(self, queries: np.ndarray, top_k: int) -> tuple[np.ndarray, np.ndarray]:
        if self._index is None or self.n_items < 1:
            raise RuntimeError("索引尚未构建或加载")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top_k 必须是正整数")
        source_queries = self._as_2d_f32(queries)
        q = self._prepare(source_queries)
        if self.variant == "pq_rerank":
            return self._search_with_exact_rerank(source_queries, q, min(top_k, self.n_items))
        distances, indices = self._index.search(q, min(top_k, self.n_items))
        if self.metric == "cosine":
            distances = np.clip(1.0 - distances, 0.0, 2.0)
        return indices, distances

    def save(self, path: str) -> None:
        import faiss

        faiss.write_index(self._index, path)

    def load(self, path: str) -> None:
        import faiss

        try:
            index = faiss.read_index(path)
        except RuntimeError as exc:
            raise ValueError("无法读取 FAISS 索引文件") from exc
        if index.d != self.dim:
            raise ValueError(f"索引维度应为 {self.dim}，实际为 {index.d}")
        if index.metric_type != self._metric_flag():
            raise ValueError("索引距离度量与清单不一致")
        self._index = index
        self.n_items = index.ntotal

    def attach_vectors(self, vectors: np.ndarray) -> None:
        if self.variant != "pq_rerank":
            return
        source = self._as_2d_f32(vectors)
        if self.n_items and source.shape[0] != self.n_items:
            raise ValueError("精确重排向量数量与索引不一致")
        self._rerank_vectors = source

    def parameters(self) -> dict:
        if self._index is None:
            return {}
        if self.variant == "ivf":
            return {"nlist": int(self._index.nlist), "nprobe": int(self._index.nprobe)}
        if self.variant == "hnsw":
            return {
                "ef_construction": int(self._index.hnsw.efConstruction),
                "ef_search": int(self._index.hnsw.efSearch),
            }
        if self.variant in {"pq", "pq_rerank"}:
            parameters = {"m": int(self._index.pq.M), "nbits": int(self._index.pq.nbits)}
            if self.variant == "pq_rerank":
                parameters["rerank_factor"] = self.RERANK_FACTOR
            return parameters
        return {}

    def size_bytes(self) -> int:
        if self._index is None:
            return 0
        import faiss

        return int(faiss.serialize_index(self._index).nbytes)

    def fingerprint(self) -> str:
        if self._index is None:
            return super().fingerprint()
        import faiss

        serialized = faiss.serialize_index(self._index)
        return hashlib.sha256(serialized.tobytes()).hexdigest()

    def _search_with_exact_rerank(
        self,
        source_queries: np.ndarray,
        prepared_queries: np.ndarray,
        top_k: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        if not hasattr(self, "_rerank_vectors"):
            raise RuntimeError("精确重排索引缺少源向量")
        candidate_k = min(self.n_items, max(top_k, top_k * self.RERANK_FACTOR))
        _, candidate_ids = self._index.search(prepared_queries, candidate_k)
        result_ids = np.empty((source_queries.shape[0], top_k), dtype=np.int64)
        result_values = np.empty((source_queries.shape[0], top_k), dtype=np.float32)

        for row, raw_query in enumerate(source_queries):
            candidates = candidate_ids[row]
            candidates = candidates[candidates >= 0]
            if candidates.size < top_k:
                raise RuntimeError("PQ 候选数量不足，无法完成精确重排")
            values = self._exact_values(raw_query, self._rerank_vectors[candidates])
            order = np.argsort(-values if self.metric == "ip" else values, kind="stable")[:top_k]
            result_ids[row] = candidates[order]
            result_values[row] = values[order]
        return result_ids, result_values

    def _exact_values(self, query: np.ndarray, candidates: np.ndarray) -> np.ndarray:
        if self.metric == "l2":
            difference = candidates - query
            return np.einsum("ij,ij->i", difference, difference).astype(np.float32)
        if self.metric == "ip":
            return (candidates @ query).astype(np.float32)

        numerator = candidates @ query
        denominator = np.linalg.norm(candidates, axis=1) * np.linalg.norm(query)
        similarities = np.divide(
            numerator,
            denominator,
            out=np.zeros_like(numerator, dtype=np.float32),
            where=denominator > 0,
        )
        return np.clip(1.0 - similarities, 0.0, 2.0).astype(np.float32)
