"""Lightweight API tests for POST /api/eval."""

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


def test_eval_flat_returns_correct_structure(client):
    response = client.post(
        "/api/eval",
        json={"index_types": ["flat"], "top_k": 5, "n_queries": 20, "metric": "l2"},
    )
    assert response.status_code == 200

    body = response.get_json()
    assert "results" in body
    assert body["metric"] == "l2"
    assert body["top_k"] == 5
    assert body["n_queries"] == 20

    assert len(body["results"]) == 1
    row = body["results"][0]
    assert row["index_type"] == "flat"
    assert row["recall_at_k"] == 1.0
    assert row["top_k"] == 5
    assert isinstance(row["avg_query_ms"], float)
    assert isinstance(row["build_ms"], float)


def test_eval_flat_self_recall_is_1(client):
    response = client.post(
        "/api/eval",
        json={"index_types": ["flat"], "top_k": 10, "n_queries": 50},
    )
    assert response.status_code == 200
    row = response.get_json()["results"][0]
    assert row["recall_at_k"] == 1.0


def test_eval_multiple_index_types(client):
    response = client.post(
        "/api/eval",
        json={"index_types": ["flat", "hnsw"], "top_k": 5, "n_queries": 10},
    )
    assert response.status_code == 200
    assert len(response.get_json()["results"]) == 2


def test_eval_rejects_unknown_index_type(client):
    response = client.post(
        "/api/eval",
        json={"index_types": ["unknown_algo"], "top_k": 5, "n_queries": 10},
    )
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_eval_rejects_mixed_valid_invalid(client):
    response = client.post(
        "/api/eval",
        json={"index_types": ["flat", "bad_type"], "top_k": 5, "n_queries": 10},
    )
    assert response.status_code == 400


def test_eval_rejects_empty_index_types(client):
    response = client.post(
        "/api/eval",
        json={"index_types": [], "top_k": 5, "n_queries": 10},
    )
    assert response.status_code == 400


def test_eval_rejects_invalid_metric(client):
    response = client.post(
        "/api/eval",
        json={"index_types": ["flat"], "metric": "manhattan"},
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"index_types": [1]},
        {"index_types": ["flat"], "top_k": 0},
        {"index_types": ["flat"], "top_k": "bad"},
        {"index_types": ["flat"], "n_queries": 0},
    ],
)
def test_eval_rejects_malformed_values(client, payload):
    response = client.post("/api/eval", json=payload)

    assert response.status_code == 400
    assert "error" in response.get_json()
