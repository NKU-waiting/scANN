"""数据管理模块（骨架）。

职责：
- 读取 `.h5ad`（AnnData）单细胞数据，取出细胞 × 基因表达矩阵 / 降维后的向量
- 格式校验与基础预处理
- 无真实数据时，生成可复现的假高维向量，保证最小检索流程可跑通

后续可在此接入真实预处理流程：QC → 标准化 → 对数变换 → 高变基因 → 缩放 → PCA。
"""
from __future__ import annotations

from dataclasses import dataclass, field

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
    if use_obsm and use_obsm in adata.obsm:
        vectors = np.asarray(adata.obsm[use_obsm], dtype=np.float32)
    else:
        X = adata.X
        vectors = np.asarray(X.todense() if hasattr(X, "todense") else X, dtype=np.float32)

    cell_ids = [str(i) for i in adata.obs_names]
    obs = {col: adata.obs[col].astype(str).tolist() for col in adata.obs.columns}
    name = path.split("/")[-1]
    return CellDataset(name=name, vectors=vectors, cell_ids=cell_ids, obs=obs)


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
