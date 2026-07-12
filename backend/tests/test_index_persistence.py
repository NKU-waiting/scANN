"""Regression tests for dataset-bound persisted ANN index artifacts."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

from app import create_app
from app.core.config import Config
from app.services.search import search_service


@pytest.fixture()
def app_config(tmp_path):
    class IndexTestConfig(Config):
        TESTING = True
        SECRET_KEY = "test-secret-key-with-at-least-thirty-two-bytes"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'test.db'}"
        DATA_DIR = str(tmp_path / "data")
        INDEX_DIR = str(tmp_path / "indices")
        LOG_TO_FILE = False
        DEMO_N_CELLS = 320
        DEMO_DIM = 16

    return IndexTestConfig


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


def _npy_upload(rows: int = 24, dim: int = 6):
    stream = BytesIO()
    np.save(stream, np.arange(rows * dim, dtype=np.float32).reshape(rows, dim))
    stream.seek(0)
    return stream, "managed.npy"


def _h5ad_with_two_representations(tmp_path) -> bytes:
    ad = pytest.importorskip("anndata")
    path = tmp_path / "representations.h5ad"
    adata = ad.AnnData(X=np.zeros((4, 2), dtype=np.float32))
    adata.obs_names = ["q", "a-neighbor", "b-neighbor", "far"]
    adata.obsm["A"] = np.asarray([[0, 0], [1, 0], [5, 0], [20, 0]], dtype=np.float32)
    adata.obsm["B"] = np.asarray([[0, 0], [5, 0], [1, 0], [20, 0]], dtype=np.float32)
    adata.write_h5ad(path)
    return path.read_bytes()


def test_flat_index_round_trip_has_verified_relative_manifest(client, app_config):
    headers = _headers(client)
    before = client.post(
        "/api/search",
        json={"cell_id": 0, "top_k": 5},
        headers=headers,
    ).get_json()

    saved = client.post("/api/index/save", json={"name": "baseline"}, headers=headers)
    artifact = saved.get_json()["artifact"]
    built = client.post(
        "/api/index/build",
        json={"index_type": "hnsw", "metric": "l2"},
        headers=headers,
    )
    loaded = client.post(
        "/api/index/load",
        json={"index_id": artifact["id"]},
        headers=headers,
    )
    after = client.post(
        "/api/search",
        json={"cell_id": 0, "top_k": 5},
        headers=headers,
    ).get_json()

    assert saved.status_code == 201
    assert artifact["active"] is True
    assert artifact["compatible"] is True
    assert saved.get_json()["status"]["persisted"] is True
    assert built.get_json()["persisted"] is False
    assert loaded.status_code == 200
    assert loaded.get_json()["status"]["index_type"] == "flat"
    assert [row["cell_id"] for row in after["results"]] == [
        row["cell_id"] for row in before["results"]
    ]

    files = sorted(Path(app_config.INDEX_DIR).iterdir())
    assert len(files) == 2
    manifest_path = next(path for path in files if path.suffix == ".json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["artifact"] == next(path.name for path in files if path.suffix == ".npy")
    assert str(Path(app_config.INDEX_DIR)) not in manifest_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("index_type", ["faiss", "ivf", "hnsw", "pq"])
def test_faiss_index_variants_round_trip(client, index_type):
    headers = _headers(client)
    built = client.post(
        "/api/index/build",
        json={"index_type": index_type, "metric": "cosine"},
        headers=headers,
    )
    saved = client.post(
        "/api/index/save",
        json={"name": f"{index_type}-cosine"},
        headers=headers,
    )
    client.post(
        "/api/index/build",
        json={"index_type": "flat", "metric": "l2"},
        headers=headers,
    )
    loaded = client.post(
        "/api/index/load",
        json={"index_id": saved.get_json()["artifact"]["id"]},
        headers=headers,
    )

    assert built.status_code == 200
    assert saved.status_code == 201
    assert loaded.status_code == 200
    assert loaded.get_json()["status"]["index_type"] == index_type
    assert loaded.get_json()["status"]["metric"] == "cosine"


def test_index_cannot_load_for_a_different_dataset(client):
    headers = _headers(client)
    saved = client.post(
        "/api/index/save",
        json={"name": "demo-only"},
        headers=headers,
    ).get_json()["artifact"]
    uploaded = client.post(
        "/api/datasets/upload",
        data={"name": "other", "file": _npy_upload()},
        headers=headers,
        content_type="multipart/form-data",
    )

    loaded = client.post(
        "/api/index/load",
        json={"index_id": saved["id"]},
        headers=headers,
    )

    assert uploaded.status_code == 201
    assert loaded.status_code == 409
    assert "不匹配" in loaded.get_json()["error"]


def test_same_h5ad_file_with_different_obsm_cannot_share_index(client, tmp_path):
    headers = _headers(client)
    payload = _h5ad_with_two_representations(tmp_path)
    first = client.post(
        "/api/datasets/upload",
        data={
            "name": "representation-a",
            "use_obsm": "A",
            "file": (BytesIO(payload), "representations.h5ad"),
        },
        headers=headers,
        content_type="multipart/form-data",
    ).get_json()["dataset"]
    artifact = client.post(
        "/api/index/save",
        json={"name": "representation-a-index"},
        headers=headers,
    ).get_json()["artifact"]
    second = client.post(
        "/api/datasets/upload",
        data={
            "name": "representation-b",
            "use_obsm": "B",
            "file": (BytesIO(payload), "representations.h5ad"),
        },
        headers=headers,
        content_type="multipart/form-data",
    ).get_json()["dataset"]

    before = client.post(
        "/api/search",
        json={"cell_id": 0, "top_k": 1},
        headers=headers,
    ).get_json()
    loaded = client.post(
        "/api/index/load",
        json={"index_id": artifact["id"]},
        headers=headers,
    )
    after = client.post(
        "/api/search",
        json={"cell_id": 0, "top_k": 1},
        headers=headers,
    ).get_json()

    assert first["fingerprint"] != second["fingerprint"]
    assert before["results"][0]["cell_id"] == 2
    assert loaded.status_code == 409
    assert after["results"][0]["cell_id"] == 2


def test_corrupt_artifact_is_rejected_without_replacing_active_index(client, app_config):
    headers = _headers(client)
    saved = client.post(
        "/api/index/save",
        json={"name": "will-corrupt"},
        headers=headers,
    ).get_json()["artifact"]
    client.post(
        "/api/index/build",
        json={"index_type": "hnsw", "metric": "l2"},
        headers=headers,
    )
    before = client.get("/api/index/status", headers=headers).get_json()
    artifact_path = next(Path(app_config.INDEX_DIR).glob("*.npy"))
    artifact_path.write_bytes(b"corrupt")

    loaded = client.post(
        "/api/index/load",
        json={"index_id": saved["id"]},
        headers=headers,
    )
    after = client.get("/api/index/status", headers=headers).get_json()

    assert loaded.status_code == 409
    assert after == before


def test_active_index_is_protected_then_can_be_deleted(client, app_config):
    headers = _headers(client)
    artifact = client.post(
        "/api/index/save",
        json={"name": "delete-me"},
        headers=headers,
    ).get_json()["artifact"]

    protected = client.delete(
        f"/api/index/artifacts/{artifact['id']}",
        headers=headers,
    )
    client.post(
        "/api/index/build",
        json={"index_type": "hnsw"},
        headers=headers,
    )
    deleted = client.delete(
        f"/api/index/artifacts/{artifact['id']}",
        headers=headers,
    )
    listed = client.get("/api/index/artifacts", headers=headers).get_json()["artifacts"]

    assert protected.status_code == 409
    assert deleted.status_code == 200
    assert listed == []
    assert list(Path(app_config.INDEX_DIR).glob("*")) == []


def test_dataset_deletion_cascades_artifact_files_and_records(client, app_config):
    headers = _headers(client)
    dataset = client.post(
        "/api/datasets/upload",
        data={"name": "indexed", "file": _npy_upload()},
        headers=headers,
        content_type="multipart/form-data",
    ).get_json()["dataset"]
    client.post("/api/index/save", json={"name": "managed-index"}, headers=headers)
    client.post("/api/datasets/demo/activate", headers=headers)

    deleted = client.delete(f"/api/datasets/{dataset['id']}", headers=headers)
    listed = client.get("/api/index/artifacts", headers=headers).get_json()["artifacts"]

    assert deleted.status_code == 200
    assert listed == []
    assert list(Path(app_config.INDEX_DIR).glob("*")) == []


def test_saved_artifact_can_be_loaded_after_application_restart(app_config):
    search_service.reset()
    first_app = create_app(app_config)
    with first_app.test_client() as first_client:
        headers = _headers(first_client)
        artifact = first_client.post(
            "/api/index/save",
            json={"name": "restart-index"},
            headers=headers,
        ).get_json()["artifact"]

    search_service.reset()
    second_app = create_app(app_config)
    with second_app.test_client() as second_client:
        headers = _headers(second_client)
        loaded = second_client.post(
            "/api/index/load",
            json={"index_id": artifact["id"]},
            headers=headers,
        )
        searched = second_client.post(
            "/api/search",
            json={"cell_id": 0, "top_k": 3},
            headers=headers,
        )

    assert loaded.status_code == 200
    assert searched.status_code == 200
    search_service.reset()


def test_duplicate_index_name_is_rejected_without_orphans(client, app_config):
    headers = _headers(client)
    first = client.post("/api/index/save", json={"name": "same"}, headers=headers)
    duplicate = client.post("/api/index/save", json={"name": "SAME"}, headers=headers)

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert len(list(Path(app_config.INDEX_DIR).glob("*"))) == 2


def test_regular_user_can_save_and_load_but_not_delete(client):
    client.post("/api/auth/register", json={"username": "user", "password": "pass123"})
    headers = _headers(client, "user", "pass123")
    saved = client.post("/api/index/save", json={"name": "user-index"}, headers=headers)
    artifact_id = saved.get_json()["artifact"]["id"]
    client.post(
        "/api/index/build",
        json={"index_type": "hnsw"},
        headers=headers,
    )
    loaded = client.post(
        "/api/index/load",
        json={"index_id": artifact_id},
        headers=headers,
    )
    deleted = client.delete(f"/api/index/artifacts/{artifact_id}", headers=headers)

    assert saved.status_code == 201
    assert loaded.status_code == 200
    assert deleted.status_code == 403
