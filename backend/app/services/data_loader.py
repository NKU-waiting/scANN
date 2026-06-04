"""数据管理模块（骨架）。

职责：
- 读取 `.h5ad`（AnnData）单细胞数据，取出细胞 × 基因表达矩阵 / 降维后的向量
- 格式校验与基础预处理
- 无真实数据时，生成可复现的假高维向量，保证最小检索流程可跑通

后续可在此接入真实预处理流程：QC → 标准化 → 对数变换 → 高变基因 → 缩放 → PCA。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class CellDataset:
    """内存中的单细胞向量数据集。"""

    name: str
    vectors: np.ndarray                 # shape: (n_cells, dim), float32
    cell_ids: list[str]                 # 每个细胞的标识
    obs: dict[str, list] = field(default_factory=dict)   # 元数据，如 cell_type

    @property
    def n_cells(self) -> int:
        return int(self.vectors.shape[0])

    @property
    def dim(self) -> int:
        return int(self.vectors.shape[1])


def load_h5ad(path: str, use_obsm: str | None = "X_pca") -> CellDataset:
    """从 .h5ad 文件加载数据集。

    优先使用降维结果 `obsm[use_obsm]`（如 X_pca），否则回退到表达矩阵 X。
    """
    import anndata as ad  # 延迟导入，避免无依赖时整体不可用

    adata = ad.read_h5ad(path)
    if use_obsm:
        if use_obsm in adata.obsm:
            source = f"obsm[{use_obsm}]"
            vectors = _to_float32_matrix(adata.obsm[use_obsm], source)
        elif use_obsm == "X_pca":
            source = "X"
            X = adata.X
            vectors = _to_float32_matrix(X, source)
        else:
            raise ValueError(f"obsm 字段不存在: {use_obsm}")
    else:
        source = "X"
        X = adata.X
        vectors = _to_float32_matrix(X, source)

    cell_ids = [str(i) for i in adata.obs_names]
    vectors = _validate_vectors(vectors, len(cell_ids), source)
    obs = {col: adata.obs[col].astype(str).tolist() for col in adata.obs.columns}
    name = Path(path).name
    return CellDataset(name=name, vectors=vectors, cell_ids=cell_ids, obs=obs)


def _to_float32_matrix(values, source: str) -> np.ndarray:
    """Convert AnnData matrix-like values into a float32 ndarray."""
    if hasattr(values, "toarray"):
        values = values.toarray()
    elif hasattr(values, "todense"):
        values = values.todense()
    try:
        return np.asarray(values, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source} 无法转换为 float32 向量矩阵") from exc


def _validate_vectors(vectors: np.ndarray, n_obs: int, source: str) -> np.ndarray:
    """Validate the cell-by-feature vector matrix used for indexing."""
    if vectors.ndim != 2:
        raise ValueError(f"{source} 必须是二维矩阵，收到 {vectors.ndim} 维")
    if vectors.shape[0] == 0:
        raise ValueError("数据集为空：至少需要 1 个细胞")
    if vectors.shape[1] == 0:
        raise ValueError("向量维度异常：至少需要 1 个特征")
    if vectors.shape[0] != n_obs:
        raise ValueError(
            f"向量行数与细胞数量不一致：向量 {vectors.shape[0]} 行，细胞 {n_obs} 个"
        )
    if not np.isfinite(vectors).all():
        raise ValueError("向量数据包含 NaN 或 Inf")
    return np.ascontiguousarray(vectors, dtype=np.float32)


def make_demo_dataset(n_cells: int = 2000, dim: int = 50, n_types: int = 5,
                      seed: int = 42) -> CellDataset:
    """生成可复现的演示数据集：若干高斯簇模拟不同细胞类型。"""
    rng = np.random.default_rng(seed)
    centers = rng.normal(0, 10, size=(n_types, dim)).astype(np.float32)
    labels = rng.integers(0, n_types, size=n_cells)
    vectors = (centers[labels] + rng.normal(0, 1, size=(n_cells, dim))).astype(np.float32)
    cell_ids = [f"cell_{i}" for i in range(n_cells)]
    obs = {"cell_type": [f"type_{t}" for t in labels.tolist()]}
    return CellDataset(name="demo", vectors=vectors, cell_ids=cell_ids, obs=obs)
