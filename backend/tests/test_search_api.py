"""API regression tests for retrieval and index-building contracts."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.core.config import Config
from app.services.search import search_service


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret-key-with-at-least-thirty-two-bytes"


@pytest.fixture()
def client():
    """Return a Flask test client with a fresh in-process search service."""
    search_service.reset()
    app = create_app(TestConfig)

    with app.test_client() as test_client:
        login = test_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        token = login.get_json()["token"]
        test_client.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        yield test_client

    search_service.reset()


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


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"cell_id": 0, "vector": [0.0] * 50},
        {"cell_id": 0, "top_k": 0},
        {"cell_id": 0, "top_k": "not-an-integer"},
        {"cell_id": True},
        {"vector": 1.0},
        {"vector": [[0.0] * 50]},
        {"cell_id": 0, "metric": "manhattan"},
        {"cell_id": 0, "index_type": "unknown"},
    ],
)
def test_search_returns_400_for_malformed_requests(client, payload):
    response = client.post("/api/search", json=payload)

    assert response.status_code == 400
    assert "error" in response.get_json()


def test_cosine_search_has_explicit_score_semantics(client):
    response = client.post(
        "/api/search",
        json={"cell_id": 0, "top_k": 3, "index_type": "flat", "metric": "cosine"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["metric"] == "cosine"
    assert payload["score_kind"] == "cosine_distance"
    assert payload["higher_is_better"] is False


def test_failed_index_build_keeps_previous_ready_index(client):
    before = client.get("/api/index/status").get_json()

    response = client.post(
        "/api/index/build",
        json={"index_type": "unknown", "metric": "l2"},
    )

    assert response.status_code == 400
    after = client.get("/api/index/status").get_json()
    assert after == before


def test_filtered_search_guarantees_type_and_requested_count(client):
    response = client.post(
        "/api/search",
        json={
            "cell_id": 0,
            "top_k": 20,
            "index_type": "ivf",
            "metric": "l2",
            "cell_type": "type_1",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["filter_strategy"] == "exact_subset"
    assert payload["returned"] == 20
    assert {row["cell_type"] for row in payload["results"]} == {"type_1"}
