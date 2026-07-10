"""Lightweight API tests for /api/auth endpoints."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.core.config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret"


@pytest.fixture()
def client():
    app = create_app(TestConfig)
    with app.test_client() as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------

def test_register_success(client):
    resp = client.post("/api/auth/register", json={"username": "alice", "password": "pass123"})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["user"]["username"] == "alice"
    assert body["user"]["role"] == "user"


def test_register_duplicate_username(client):
    client.post("/api/auth/register", json={"username": "bob", "password": "pass123"})
    resp = client.post("/api/auth/register", json={"username": "bob", "password": "other123"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_register_missing_fields(client):
    resp = client.post("/api/auth/register", json={"username": "carol"})
    assert resp.status_code == 400


def test_register_short_password(client):
    resp = client.post("/api/auth/register", json={"username": "dave", "password": "123"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 登录
# ---------------------------------------------------------------------------

def test_login_success(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "pass123"})
    resp = client.post("/api/auth/login", json={"username": "alice", "password": "pass123"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert "token" in body
    assert body["user"]["username"] == "alice"


def test_login_wrong_password(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "pass123"})
    resp = client.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_login_nonexistent_user(client):
    resp = client.post("/api/auth/login", json={"username": "nobody", "password": "pass123"})
    assert resp.status_code == 400


def test_login_missing_fields(client):
    resp = client.post("/api/auth/login", json={"username": "alice"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 鉴权失败
# ---------------------------------------------------------------------------

def test_protected_route_no_token(client):
    resp = client.get("/api/auth/users")
    assert resp.status_code == 401


def test_protected_route_invalid_token(client):
    resp = client.get("/api/auth/users", headers={"Authorization": "Bearer invalid.token.here"})
    assert resp.status_code == 401


def test_protected_route_malformed_header(client):
    resp = client.get("/api/auth/users", headers={"Authorization": "Token abc"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# admin 权限校验
# ---------------------------------------------------------------------------

def _admin_token(client) -> str:
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.get_json()["token"]


def _user_token(client, username="alice") -> str:
    client.post("/api/auth/register", json={"username": username, "password": "pass123"})
    resp = client.post("/api/auth/login", json={"username": username, "password": "pass123"})
    return resp.get_json()["token"]


def test_admin_can_list_users(client):
    token = _admin_token(client)
    resp = client.get("/api/auth/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert isinstance(resp.get_json()["users"], list)


def test_non_admin_cannot_list_users(client):
    token = _user_token(client)
    resp = client.get("/api/auth/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_admin_can_delete_user(client):
    _user_token(client, "to_delete")
    admin_token = _admin_token(client)

    users_resp = client.get("/api/auth/users", headers={"Authorization": f"Bearer {admin_token}"})
    users = users_resp.get_json()["users"]
    target = next(u for u in users if u["username"] == "to_delete")

    resp = client.delete(
        f"/api/auth/users/{target['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200


def test_non_admin_cannot_delete_user(client):
    _user_token(client, "victim")
    actor_token = _user_token(client, "actor")

    admin_token = _admin_token(client)
    users_resp = client.get("/api/auth/users", headers={"Authorization": f"Bearer {admin_token}"})
    users = users_resp.get_json()["users"]
    target = next(u for u in users if u["username"] == "victim")

    resp = client.delete(
        f"/api/auth/users/{target['id']}",
        headers={"Authorization": f"Bearer {actor_token}"},
    )
    assert resp.status_code == 403


def test_delete_nonexistent_user(client):
    token = _admin_token(client)
    resp = client.delete("/api/auth/users/99999", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
