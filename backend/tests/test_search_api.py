"""Lightweight API smoke tests for the mid-term demo flow."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.services.search import search_service


@pytest.fixture()
def client():
    """Return a Flask test client with a fresh in-process search service."""
    search_service.dataset = None
    search_service.index = None
    search_service.index_type = "flat"
    search_service.metric = "l2"

    app = create_app()
    app.config.update(TESTING=True)

    with app.test_client() as test_client:
        yield test_client

    search_service.dataset = None
    search_service.index = None
    search_service.index_type = "flat"
    search_service.metric = "l2"


def test_health_check(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "service": "scANN",
        "status": "ok",
        "version": "0.1.0",
    }


def test_build_index_returns_status_and_build_time(client):
    response = client.post(
        "/api/index/build",
        json={"index_type": "flat", "metric": "l2"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ready"] is True
    assert payload["dataset"] == "demo"
    assert payload["n_cells"] > 0
    assert payload["dim"] > 0
    assert payload["index"] == "flat(l2)"
    assert payload["metadata_fields"] == ["cell_type"]
    assert isinstance(payload["build_ms"], (int, float))


def test_search_by_cell_returns_top_k_results(client):
    response = client.post(
        "/api/search",
        json={"cell_id": 0, "top_k": 5, "index_type": "flat", "metric": "l2"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["index"] == "flat(l2)"
    assert payload["returned"] == 5
    assert isinstance(payload["query_ms"], (int, float))
    assert len(payload["results"]) == 5
    assert {
        "cell_id",
        "cell_name",
        "cell_type",
        "distance",
    } <= payload["results"][0].keys()


@pytest.mark.parametrize(
    ("payload", "error_text"),
    [
        ({"top_k": 5, "index_type": "flat", "metric": "l2"}, "需提供 cell_id 或 vector"),
        ({"cell_id": -1, "top_k": 5, "index_type": "flat", "metric": "l2"}, "cell_id 越界"),
        ({"vector": [0.1, 0.2], "top_k": 5, "index_type": "flat", "metric": "l2"}, "向量维度应为"),
    ],
)
def test_search_rejects_invalid_parameters(client, payload, error_text):
    response = client.post("/api/search", json=payload)

    assert response.status_code == 400
    assert error_text in response.get_json()["error"]
