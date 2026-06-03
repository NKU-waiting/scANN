"""索引抽象接口。

所有 ANN / 精确索引实现都遵循该接口，使检索服务与具体算法解耦。
"""
from __future__ import annotations

import abc

import numpy as np


class BaseIndex(abc.ABC):
    """向量索引统一接口。

    约定：
    - metric: "l2"(欧氏距离) 或 "ip"(内积/余弦)
    - search 返回 (indices, distances)，均为 shape (n_queries, top_k)
    """

    def __init__(self, dim: int, metric: str = "l2"):
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

    @staticmethod
    def _as_2d_f32(arr: np.ndarray) -> np.ndarray:
        arr = np.asarray(arr, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        return arr
