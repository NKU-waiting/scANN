"""索引抽象接口。

所有 ANN / 精确索引实现都遵循该接口，使检索服务与具体算法解耦。
"""

from __future__ import annotations

import abc
import hashlib

import numpy as np

VALID_METRICS = frozenset({"l2", "cosine", "ip"})


class BaseIndex(abc.ABC):
    """向量索引统一接口。

    约定：
    - metric: "l2"（平方欧氏距离）、"cosine"（余弦距离）或 "ip"（内积）
    - search 返回 (indices, distances)，均为 shape (n_queries, top_k)
    """

    def __init__(self, dim: int, metric: str = "l2"):
        if not isinstance(dim, int) or isinstance(dim, bool) or dim < 1:
            raise ValueError("向量维度必须是正整数")
        if metric not in VALID_METRICS:
            valid = ", ".join(sorted(VALID_METRICS))
            raise ValueError(f"未知距离度量: {metric}（支持 {valid}）")
        self.dim = dim
        self.metric = metric
        self.n_items = 0

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """索引类型名，用于状态展示。"""

    @abc.abstractmethod
    def build(self, vectors: np.ndarray) -> None:
        """用全部向量构建索引。"""

    @abc.abstractmethod
    def search(self, queries: np.ndarray, top_k: int) -> tuple[np.ndarray, np.ndarray]:
        """检索 Top-K，返回 (indices, distances)。"""

    @abc.abstractmethod
    def save(self, path: str) -> None:
        """持久化索引到磁盘。"""

    @abc.abstractmethod
    def load(self, path: str) -> None:
        """从磁盘加载索引。"""

    def parameters(self) -> dict:
        """Return serializable algorithm parameters for persistence manifests."""
        return {}

    def size_bytes(self) -> int:
        """Return a stable serialized-size proxy for index memory comparisons."""
        return 0

    def fingerprint(self) -> str:
        """Return a SHA-256 digest of the serialized index representation."""
        return hashlib.sha256(b"").hexdigest()

    def attach_vectors(self, vectors: np.ndarray) -> None:
        """Attach validated source vectors when an algorithm needs exact refinement."""

    def _as_2d_f32(self, arr: np.ndarray) -> np.ndarray:
        try:
            arr = np.asarray(arr, dtype=np.float32)
        except (TypeError, ValueError) as exc:
            raise ValueError("向量必须是有限数值") from exc
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        if arr.ndim != 2:
            raise ValueError("向量必须是一维向量或二维向量矩阵")
        if arr.shape[0] < 1 or arr.shape[1] != self.dim:
            raise ValueError(f"向量维度应为 {self.dim}")
        if not np.isfinite(arr).all():
            raise ValueError("向量必须是有限数值")
        return np.ascontiguousarray(arr, dtype=np.float32)

    def _prepare(self, arr: np.ndarray) -> np.ndarray:
        """Validate vectors and normalize them when cosine distance is requested."""
        prepared = self._as_2d_f32(arr)
        if self.metric != "cosine":
            return prepared
        norms = np.linalg.norm(prepared, axis=1, keepdims=True)
        return np.divide(
            prepared,
            norms,
            out=np.zeros_like(prepared),
            where=norms > 0,
        )
