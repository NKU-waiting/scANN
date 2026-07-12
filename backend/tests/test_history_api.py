"""Regression tests for durable query and evaluation history."""

from __future__ import annotations

import pytest

from app import create_app
from app.core.config import Config
from app.services.search import search_service


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret-key-with-at-least-thirty-two-bytes"
    LOG_TO_FILE = False
    DEMO_N_CELLS = 80
    DEMO_DIM = 6


@pytest.fixture()
def client():
    search_service.reset()
    app = create_app(TestConfig)
    with app.test_client() as test_client:
        yield test_client
    search_service.reset()


def _register_and_headers(client, username: str) -> dict:
    client.post(
        "/api/auth/register",
        json={"username": username, "password": "pass123"},
    )
    login = client.post(
        "/api/auth/login",
        json={"username": username, "password": "pass123"},
    )
    return {"Authorization": f"Bearer {login.get_json()['token']}"}


def _admin_headers(client) -> dict:
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    return {"Authorization": f"Bearer {login.get_json()['token']}"}


def test_query_history_records_normalized_request_without_raw_vector(client):
    headers = _register_and_headers(client, "alice")
    cell_query = client.post(
        "/api/search",
        json={"cell_id": "2", "top_k": "4", "cell_type": "type_1"},
        headers=headers,
    )
    vector_query = client.post(
        "/api/search",
        json={"vector": [0.0] * 6, "top_k": 3},
        headers=headers,
    )
    history = client.get("/api/history/queries", headers=headers)

    assert cell_query.status_code == 200
    assert vector_query.status_code == 200
    assert isinstance(cell_query.get_json()["query_id"], int)
    records = history.get_json()["queries"]
    assert len(records) == 2
    assert records[0]["query_mode"] == "vector"
    assert records[0]["query_cell_id"] is None
    assert records[1]["query_cell_id"] == 2
    assert records[1]["top_k"] == 4
    assert records[1]["filters"] == {"cell_type": "type_1"}
    assert all("vector" not in record for record in records)


def test_regular_users_only_see_their_history_while_admin_sees_all(client):
    alice = _register_and_headers(client, "alice")
    bob = _register_and_headers(client, "bob")
    client.post("/api/search", json={"cell_id": 0}, headers=alice)
    client.post("/api/search", json={"cell_id": 1}, headers=bob)

    alice_records = client.get("/api/history/queries", headers=alice).get_json()["queries"]
    admin_records = client.get(
        "/api/history/queries",
        headers=_admin_headers(client),
    ).get_json()["queries"]

    assert len(alice_records) == 1
    assert len(admin_records) == 2
    assert alice_records[0]["user_id"] != next(
        record["user_id"]
        for record in admin_records
        if record["user_id"] != alice_records[0]["user_id"]
    )


def test_deleting_user_atomically_removes_query_and_evaluation_history(client):
    user_headers = _register_and_headers(client, "retired")
    client.post("/api/search", json={"cell_id": 0}, headers=user_headers)
    client.post(
        "/api/eval",
        json={"index_types": ["flat"], "top_k": 3, "n_queries": 3},
        headers=user_headers,
    )

    admin_headers = _admin_headers(client)
    users = client.get("/api/auth/users", headers=admin_headers).get_json()["users"]
    retired = next(user for user in users if user["username"] == "retired")
    deleted = client.delete(f"/api/auth/users/{retired['id']}", headers=admin_headers)
    queries = client.get("/api/history/queries", headers=admin_headers).get_json()["queries"]
    evaluations = client.get(
        "/api/history/evaluations",
        headers=admin_headers,
    ).get_json()["evaluations"]

    assert deleted.status_code == 200
    assert all(record["user_id"] != retired["id"] for record in queries)
    assert all(record["user_id"] != retired["id"] for record in evaluations)


def test_evaluation_history_persists_result_snapshot(client):
    headers = _register_and_headers(client, "evaluator")
    evaluated = client.post(
        "/api/eval",
        json={"index_types": ["flat", "hnsw"], "top_k": 5, "n_queries": 10},
        headers=headers,
    )
    history = client.get("/api/history/evaluations", headers=headers)

    assert evaluated.status_code == 200
    assert isinstance(evaluated.get_json()["evaluation_id"], int)
    records = history.get_json()["evaluations"]
    assert len(records) == 1
    assert records[0]["index_types"] == ["flat", "hnsw"]
    assert records[0]["n_queries"] == 10
    assert len(records[0]["results"]) == 2


@pytest.mark.parametrize(
    "path",
    ["/api/history/queries?limit=0", "/api/history/evaluations?limit=101"],
)
def test_history_limit_is_bounded(client, path):
    response = client.get(path, headers=_admin_headers(client))

    assert response.status_code == 400
