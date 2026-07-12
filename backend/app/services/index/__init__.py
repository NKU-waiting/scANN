"""可插拔索引层。

通过 `create_index(index_type, dim, metric)` 工厂获取实现，
新增 ANN 算法只需实现 BaseIndex 接口并在此注册。
"""
from .base import BaseIndex, VALID_METRICS
from .flat_index import FlatIndex

VALID_INDEX_TYPES = frozenset({"flat", "faiss", "ivf", "hnsw", "pq"})

__all__ = [
    "BaseIndex",
    "FlatIndex",
    "VALID_INDEX_TYPES",
    "VALID_METRICS",
    "create_index",
]


def create_index(index_type: str, dim: int, metric: str = "l2") -> BaseIndex:
    index_type = (index_type or "flat").lower()
    if index_type == "flat":
        return FlatIndex(dim=dim, metric=metric)
    if index_type in ("faiss", "ivf", "hnsw", "pq"):
        # 延迟导入：仅在请求 faiss 时才依赖 faiss 库
        from .faiss_index import FaissIndex
        return FaissIndex(dim=dim, metric=metric, variant=index_type)
    raise ValueError(f"未知索引类型: {index_type}")
