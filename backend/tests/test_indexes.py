"""Unit tests for exact and FAISS index contracts."""

from __future__ import annotations

import numpy as np
import pytest

from app.services.data_loader import CellDataset
from app.services.eval import evaluate_index
from app.services.index import FlatIndex, create_index


def test_flat_cosine_distance_normalizes_vectors():
    index = FlatIndex(dim=2, metric="cosine")
    index.build(np.asarray([[1, 0], [-1, 0], [0, 3]], dtype=np.float32))

    ids, distances = index.search([2, 0], 3)

    assert ids.tolist() == [[0, 2, 1]]
    assert distances[0].tolist() == pytest.approx([0.0, 1.0, 2.0])


@pytest.mark.parametrize("index_type", ["flat", "faiss", "ivf", "hnsw", "pq"])
@pytest.mark.parametrize("metric", ["l2", "cosine", "ip"])
def test_all_index_variants_return_valid_ranked_results(index_type, metric):
    rng = np.random.default_rng(7)
    vectors = rng.normal(size=(640, 16)).astype(np.float32)
    index = create_index(index_type, dim=16, metric=metric)
    index.build(vectors)

    ids, values = index.search(vectors[0], 10)

    assert ids.shape == (1, 10)
    assert values.shape == (1, 10)
    assert np.isfinite(values).all()
    if metric == "ip":
        assert np.all(values[0, 1:] <= values[0, :-1] + 1e-6)
    else:
        assert ids[0, 0] == 0
        assert np.all(values[0, 1:] >= values[0, :-1] - 1e-6)


@pytest.mark.parametrize("metric", ["", "euclidean", "manhattan", None])
def test_index_rejects_unknown_metrics(metric):
    with pytest.raises(ValueError, match="未知距离度量"):
        FlatIndex(dim=2, metric=metric)


def test_flat_self_recall_stays_one_when_k_exceeds_dataset():
    rng = np.random.default_rng(9)
    vectors = rng.normal(size=(8, 4)).astype(np.float32)
    dataset = CellDataset(
        name="small",
        vectors=vectors,
        cell_ids=[f"cell_{i}" for i in range(8)],
    )

    result = evaluate_index(dataset, "flat", top_k=100, n_queries=100, metric="l2")

    assert result["recall_at_k"] == 1.0
    assert result["effective_top_k"] == 7
    assert result["n_queries"] == 8
