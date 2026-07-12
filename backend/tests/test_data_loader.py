"""Regression tests for supported managed dataset formats."""
from __future__ import annotations

import numpy as np
import pytest

from app.services.data_loader import load_csv, load_h5ad, load_npy


def test_load_npy_validates_and_converts_matrix(tmp_path):
    path = tmp_path / "vectors.npy"
    np.save(path, np.arange(12, dtype=np.float64).reshape(4, 3))

    dataset = load_npy(str(path))

    assert dataset.vectors.shape == (4, 3)
    assert dataset.vectors.dtype == np.float32
    assert dataset.cell_ids == ["cell_0", "cell_1", "cell_2", "cell_3"]
    assert dataset.source_format == "npy"


def test_load_npy_rejects_pickle_payload(tmp_path):
    path = tmp_path / "unsafe.npy"
    np.save(path, np.asarray([{"secret": "value"}], dtype=object))

    with pytest.raises(ValueError, match="无法读取 NPY"):
        load_npy(str(path))


def test_load_csv_supports_ids_features_and_metadata(tmp_path):
    path = tmp_path / "cells.csv"
    path.write_text(
        "cell_id,gene_a,obs:cell_type,gene_b\n"
        "cell-a,1.0,T-cell,2.0\n"
        "cell-b,3.5,B-cell,4.5\n",
        encoding="utf-8",
    )

    dataset = load_csv(str(path))

    assert dataset.cell_ids == ["cell-a", "cell-b"]
    assert dataset.obs == {"cell_type": ["T-cell", "B-cell"]}
    assert dataset.vectors.tolist() == [[1.0, 2.0], [3.5, 4.5]]


def test_load_csv_supports_headerless_numeric_matrix(tmp_path):
    path = tmp_path / "matrix.csv"
    path.write_text("1,2,3\n4,5,6\n", encoding="utf-8")

    dataset = load_csv(str(path))

    assert dataset.vectors.shape == (2, 3)
    assert dataset.cell_ids == ["cell_0", "cell_1"]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "CSV 数据为空"),
        ("a,b\n1\n", "列数必须一致"),
        ("cell_id,gene\na,not-a-number\n", "非数值特征"),
        ("cell_id,gene\na,1\na,2\n", "必须唯一"),
        ("cell_id,obs:type\na,T\n", "数值特征列"),
    ],
)
def test_load_csv_rejects_malformed_input(tmp_path, content, message):
    path = tmp_path / "invalid.csv"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_csv(str(path))


def test_load_h5ad_prefers_requested_embedding(tmp_path):
    ad = pytest.importorskip("anndata")
    path = tmp_path / "cells.h5ad"
    adata = ad.AnnData(
        X=np.ones((3, 5), dtype=np.float32),
        obs={"cell_type": ["a", "b", "c"]},
    )
    adata.obs_names = ["c1", "c2", "c3"]
    adata.obsm["X_pca"] = np.arange(6, dtype=np.float32).reshape(3, 2)
    adata.write_h5ad(path)

    dataset = load_h5ad(str(path), use_obsm="X_pca")

    assert dataset.vectors.shape == (3, 2)
    assert dataset.cell_ids == ["c1", "c2", "c3"]
    assert dataset.obs["cell_type"] == ["a", "b", "c"]
