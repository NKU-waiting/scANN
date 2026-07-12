"""API regression tests for persistent multi-dataset lifecycle management."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

from app import create_app
from app.core.config import Config
from app.services.search import search_service


@pytest.fixture()
def app_config(tmp_path):
    class DatasetTestConfig(Config):
        TESTING = True
        SECRET_KEY = "test-secret-key-with-at-least-thirty-two-bytes"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'test.db'}"
        DATA_DIR = str(tmp_path / "data")
        INDEX_DIR = str(tmp_path / "indices")
        LOG_TO_FILE = False
        DEMO_N_CELLS = 100
        DEMO_DIM = 8

    return DatasetTestConfig


@pytest.fixture()
def app(app_config):
    search_service.reset()
    application = create_app(app_config)
    yield application
    search_service.reset()


@pytest.fixture()
def client(app):
    return app.test_client()


def _token(client, username="admin", password="admin123") -> str:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.get_json()["token"]


def _headers(client, username="admin", password="admin123") -> dict:
    return {"Authorization": f"Bearer {_token(client, username, password)}"}


def _npy_upload(name: str, rows: int = 12, dim: int = 4):
    stream = BytesIO()
    values = np.arange(rows * dim, dtype=np.float32).reshape(rows, dim)
    np.save(stream, values)
    stream.seek(0)
    return stream, f"{name}.npy"


def test_upload_lists_activates_and_searches_dataset(client):
    headers = _headers(client)

    uploaded = client.post(
        "/api/datasets/upload",
        data={"name": "first", "file": _npy_upload("first")},
        headers=headers,
        content_type="multipart/form-data",
    )
    listed = client.get("/api/datasets", headers=headers)
    searched = client.post(
        "/api/search",
        json={"cell_id": 0, "top_k": 3},
        headers=headers,
    )

    assert uploaded.status_code == 201
    resource = uploaded.get_json()["dataset"]
    assert resource["name"] == "first"
    assert resource["active"] is True
    assert resource["n_cells"] == 12
    assert resource["dim"] == 4
    assert resource["fingerprint"]
    resources = listed.get_json()["datasets"]
    assert [row["name"] for row in resources] == ["demo", "first"]
    assert next(row for row in resources if row["name"] == "first")["active"] is True
    assert searched.status_code == 200
    assert searched.get_json()["returned"] == 3


def test_multiple_datasets_can_be_switched_and_deleted(client):
    admin_headers = _headers(client)
    first = client.post(
        "/api/datasets/upload",
        data={"name": "first", "file": _npy_upload("first")},
        headers=admin_headers,
        content_type="multipart/form-data",
    ).get_json()["dataset"]
    second = client.post(
        "/api/datasets/upload",
        data={"name": "second", "activate": "false", "file": _npy_upload("second", 8, 3)},
        headers=admin_headers,
        content_type="multipart/form-data",
    ).get_json()["dataset"]

    activated = client.post(
        f"/api/datasets/{second['id']}/activate",
        headers=admin_headers,
    )
    active_delete = client.delete(
        f"/api/datasets/{second['id']}",
        headers=admin_headers,
    )
    deleted = client.delete(
        f"/api/datasets/{first['id']}",
        headers=admin_headers,
    )
    resources = client.get("/api/datasets", headers=admin_headers).get_json()["datasets"]

    assert activated.status_code == 200
    assert activated.get_json()["status"]["dataset"] == "second"
    assert active_delete.status_code == 409
    assert deleted.status_code == 200
    assert [row["name"] for row in resources] == ["demo", "second"]


def test_only_admin_can_delete_dataset(client):
    admin_headers = _headers(client)
    resource = client.post(
        "/api/datasets/upload",
        data={"name": "protected", "activate": "false", "file": _npy_upload("protected")},
        headers=admin_headers,
        content_type="multipart/form-data",
    ).get_json()["dataset"]
    client.post("/api/auth/register", json={"username": "user", "password": "pass123"})
    user_headers = _headers(client, "user", "pass123")

    response = client.delete(f"/api/datasets/{resource['id']}", headers=user_headers)

    assert response.status_code == 403


def test_duplicate_or_invalid_upload_leaves_no_orphan_file(client, app_config):
    headers = _headers(client)
    first = client.post(
        "/api/datasets/upload",
        data={"name": "duplicate", "activate": "false", "file": _npy_upload("first")},
        headers=headers,
        content_type="multipart/form-data",
    )
    duplicate = client.post(
        "/api/datasets/upload",
        data={"name": "DUPLICATE", "activate": "false", "file": _npy_upload("second")},
        headers=headers,
        content_type="multipart/form-data",
    )
    invalid = client.post(
        "/api/datasets/upload",
        data={"name": "bad", "file": (BytesIO(b"not numpy"), "bad.npy")},
        headers=headers,
        content_type="multipart/form-data",
    )

    uploaded_files = list((Path(app_config.DATA_DIR) / "uploads").glob("*"))
    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert invalid.status_code == 400
    assert len(uploaded_files) == 1


@pytest.mark.parametrize("path", ["../private.h5ad", "/tmp/private.h5ad", "file.txt"])
def test_server_side_import_rejects_unsafe_paths(client, path):
    response = client.post(
        "/api/datasets/load",
        json={"path": path},
        headers=_headers(client),
    )

    assert response.status_code == 400


def test_demo_activation_allows_deleting_previously_active_dataset(client):
    headers = _headers(client)
    resource = client.post(
        "/api/datasets/upload",
        data={"name": "temporary", "file": _npy_upload("temporary")},
        headers=headers,
        content_type="multipart/form-data",
    ).get_json()["dataset"]

    demo = client.post("/api/datasets/demo/activate", headers=headers)
    deleted = client.delete(f"/api/datasets/{resource['id']}", headers=headers)

    assert demo.status_code == 200
    assert demo.get_json()["status"]["dataset"] == "demo"
    assert deleted.status_code == 200


def test_active_dataset_is_restored_after_application_restart(app_config):
    search_service.reset()
    first_app = create_app(app_config)
    with first_app.test_client() as first_client:
        headers = _headers(first_client)
        uploaded = first_client.post(
            "/api/datasets/upload",
            data={"name": "restored", "file": _npy_upload("restored", 9, 3)},
            headers=headers,
            content_type="multipart/form-data",
        )
        assert uploaded.status_code == 201

    search_service.reset()
    second_app = create_app(app_config)
    with second_app.test_client() as second_client:
        headers = _headers(second_client)
        status = second_client.get("/api/index/status", headers=headers)

    assert status.status_code == 200
    assert status.get_json()["dataset"] == "restored"
    assert status.get_json()["dim"] == 3
    search_service.reset()
