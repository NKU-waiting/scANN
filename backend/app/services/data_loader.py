"""数据管理模块（骨架）。

职责：
- 读取 `.h5ad`（AnnData）单细胞数据，取出细胞 × 基因表达矩阵 / 降维后的向量
- 格式校验与基础预处理
- 无真实数据时，生成可复现的假高维向量，保证最小检索流程可跑通

后续可在此接入真实预处理流程：QC → 标准化 → 对数变换 → 高变基因 → 缩放 → PCA。
"""
from __future__ import annotations

import csv
import hashlib
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
    record_id: int | None = None
    fingerprint: str | None = None
    source_path: str | None = None
    source_format: str = "memory"

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
    return CellDataset(
        name=name,
        vectors=vectors,
        cell_ids=cell_ids,
        obs=obs,
        source_format="h5ad",
    )


def load_npy(path: str) -> CellDataset:
    """Load a numeric cell-by-feature matrix from a safe NumPy ``.npy`` file."""
    try:
        vectors = np.load(path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise ValueError("无法读取 NPY 向量矩阵") from exc
    vectors = _to_float32_matrix(vectors, "NPY")
    vectors = _validate_vectors(vectors, vectors.shape[0] if vectors.ndim else 0, "NPY")
    cell_ids = [f"cell_{index}" for index in range(vectors.shape[0])]
    return CellDataset(
        name=Path(path).name,
        vectors=vectors,
        cell_ids=cell_ids,
        source_format="npy",
    )


def load_csv(path: str) -> CellDataset:
    """Load numeric CSV with an optional header, ``cell_id``, and ``obs:`` columns."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as stream:
            rows = [row for row in csv.reader(stream) if any(value.strip() for value in row)]
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValueError("无法读取 CSV 数据") from exc
    if not rows:
        raise ValueError("CSV 数据为空")

    width = len(rows[0])
    if width == 0 or any(len(row) != width for row in rows):
        raise ValueError("CSV 每行列数必须一致")

    has_header = not all(_is_float(value) for value in rows[0])
    header = [value.strip() for value in rows[0]] if has_header else []
    data_rows = rows[1:] if has_header else rows
    if not data_rows:
        raise ValueError("CSV 至少需要一行数据")

    id_column = None
    metadata_columns: dict[int, str] = {}
    feature_columns: list[int] = []
    if has_header:
        normalized = [value.lower() for value in header]
        if len(set(normalized)) != len(normalized) or any(not value for value in header):
            raise ValueError("CSV 表头不能为空或重复")
        for index, column in enumerate(header):
            if column.lower() == "cell_id":
                id_column = index
            elif column.lower().startswith("obs:"):
                field_name = column[4:].strip()
                if not field_name:
                    raise ValueError("obs: 元数据列必须包含字段名")
                metadata_columns[index] = field_name
            else:
                feature_columns.append(index)
    else:
        feature_columns = list(range(width))

    if not feature_columns:
        raise ValueError("CSV 至少需要一个数值特征列")

    cell_ids: list[str] = []
    metadata = {name: [] for name in metadata_columns.values()}
    numeric_rows: list[list[float]] = []
    for row_number, row in enumerate(data_rows, start=2 if has_header else 1):
        cell_id = row[id_column].strip() if id_column is not None else f"cell_{len(cell_ids)}"
        if not cell_id:
            raise ValueError(f"CSV 第 {row_number} 行 cell_id 为空")
        cell_ids.append(cell_id)
        for index, field_name in metadata_columns.items():
            metadata[field_name].append(row[index].strip())
        try:
            numeric_rows.append([float(row[index].strip()) for index in feature_columns])
        except ValueError as exc:
            raise ValueError(f"CSV 第 {row_number} 行包含非数值特征") from exc

    if len(set(cell_ids)) != len(cell_ids):
        raise ValueError("CSV cell_id 必须唯一")
    vectors = np.asarray(numeric_rows, dtype=np.float32)
    vectors = _validate_vectors(vectors, len(cell_ids), "CSV")
    return CellDataset(
        name=Path(path).name,
        vectors=vectors,
        cell_ids=cell_ids,
        obs=metadata,
        source_format="csv",
    )


def load_dataset_file(path: str, use_obsm: str | None = "X_pca") -> CellDataset:
    """Dispatch a managed data file to the matching validated loader."""
    suffix = Path(path).suffix.lower()
    if suffix == ".h5ad":
        return load_h5ad(path, use_obsm=use_obsm)
    if suffix == ".npy":
        return load_npy(path)
    if suffix == ".csv":
        return load_csv(path)
    raise ValueError("仅支持 .h5ad、.npy 或 .csv 数据文件")


def file_sha256(path: str) -> str:
    """Return a streaming SHA-256 fingerprint without retaining file contents."""
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    digest = hashlib.sha256()
    digest.update(np.ascontiguousarray(vectors).tobytes())
    digest.update("\n".join(cell_ids).encode("utf-8"))
    return CellDataset(
        name="demo",
        vectors=vectors,
        cell_ids=cell_ids,
        obs=obs,
        fingerprint=digest.hexdigest(),
        source_format="demo",
    )


def _is_float(value: str) -> bool:
    try:
        float(value.strip())
        return True
    except ValueError:
        return False
