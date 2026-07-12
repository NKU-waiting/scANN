"""Access-control and safe-runtime regression tests."""
from __future__ import annotations

import pytest

from app import create_app
from app.core.config import Config, DEVELOPMENT_SECRET
from app.services.search import search_service


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret-key-with-at-least-thirty-two-bytes"
    LOG_TO_FILE = False


@pytest.fixture()
def app():
    search_service.reset()
    application = create_app(TestConfig)
    yield application
    search_service.reset()


@pytest.fixture()
def client(app):
    return app.test_client()


def _login(client, username="admin", password="admin123") -> str:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.get_json()["token"]


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/api/index/status", None),
        ("post", "/api/index/build", {"index_type": "flat"}),
        ("get", "/api/index/artifacts", None),
        ("post", "/api/index/save", {}),
        ("post", "/api/index/load", {"index_id": 1}),
        ("get", "/api/datasets", None),
        ("post", "/api/datasets/load", {}),
        ("post", "/api/search", {"cell_id": 0}),
        ("post", "/api/eval", {"index_types": ["flat"]}),
    ],
)
def test_business_routes_require_authentication(client, method, path, payload):
    response = getattr(client, method)(path, json=payload)

    assert response.status_code == 401


def test_authenticated_user_can_use_retrieval_routes(client):
    client.post("/api/auth/register", json={"username": "reader", "password": "pass123"})
    token = _login(client, "reader", "pass123")
    headers = {"Authorization": f"Bearer {token}"}

    status_response = client.get("/api/index/status", headers=headers)
    search_response = client.post(
        "/api/search",
        json={"cell_id": 0, "top_k": 3},
        headers=headers,
    )

    assert status_response.status_code == 200
    assert search_response.status_code == 200


def test_deleted_user_token_is_immediately_invalid(client):
    client.post("/api/auth/register", json={"username": "deleted", "password": "pass123"})
    user_token = _login(client, "deleted", "pass123")
    admin_token = _login(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    users = client.get("/api/auth/users", headers=admin_headers).get_json()["users"]
    target = next(user for user in users if user["username"] == "deleted")

    deleted = client.delete(f"/api/auth/users/{target['id']}", headers=admin_headers)
    rejected = client.get(
        "/api/index/status",
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert deleted.status_code == 200
    assert rejected.status_code == 401


def test_http_errors_are_json(client):
    response = client.get("/api/not-found")

    assert response.status_code == 404
    assert response.is_json
    assert response.get_json()["status"] == 404


def test_cors_only_allows_configured_origins(client):
    allowed = client.get("/api/health", headers={"Origin": "http://127.0.0.1:5173"})
    rejected = client.get("/api/health", headers={"Origin": "https://untrusted.example"})

    assert allowed.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"
    assert "Access-Control-Allow-Origin" not in rejected.headers


def test_production_rejects_development_secret():
    class UnsafeProductionConfig(TestConfig):
        ENVIRONMENT = "production"
        SECRET_KEY = DEVELOPMENT_SECRET
        ADMIN_PASSWORD = "strong-bootstrap-password"

    with pytest.raises(RuntimeError, match="SCANN_SECRET_KEY"):
        create_app(UnsafeProductionConfig)


def test_production_rejects_default_admin_password():
    class UnsafeProductionConfig(TestConfig):
        ENVIRONMENT = "production"
        SECRET_KEY = "production-secret-key-with-at-least-thirty-two-bytes"
        ADMIN_PASSWORD = "admin123"

    with pytest.raises(RuntimeError, match="SCANN_ADMIN_PASSWORD"):
        create_app(UnsafeProductionConfig)
