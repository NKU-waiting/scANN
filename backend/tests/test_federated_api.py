"""Regression tests for joint indexes and provenance-preserving cross-dataset search."""

from __future__ import annotations

from io import BytesIO

import pytest

from app import create_app
from app.core.config import Config
from app.services.federated import federated_search_service
from app.services.search import search_service


@pytest.fixture()
def app_config(tmp_path):
    class FederatedTestConfig(Config):
        TESTING = True
        SECRET_KEY = "test-secret-key-with-at-least-thirty-two-bytes"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'test.db'}"
        DATA_DIR = str(tmp_path / "data")
        INDEX_DIR = str(tmp_path / "indices")
        LOG_TO_FILE = False
        DEMO_N_CELLS = 20
        DEMO_DIM = 2
        MAX_FEDERATED_DATASETS = 4
        MAX_FEDERATED_CELLS = 100

    return FederatedTestConfig


@pytest.fixture()
def app(app_config):
    search_service.reset()
    federated_search_service.reset()
    application = create_app(app_config)
    yield application
    federated_search_service.reset()
    search_service.reset()


@pytest.fixture()
def client(app):
    return app.test_client()


def _headers(client) -> dict:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    return {"Authorization": f"Bearer {response.get_json()['token']}"}


def _csv_upload(client, headers, name: str, rows: list[tuple], activate: bool = False):
    content = "cell_id,obs:cell_type,x,y\n" + "\n".join(
        f"{cell_id},{cell_type},{x},{y}" for cell_id, cell_type, x, y in rows
    )
    response = client.post(
        "/api/datasets/upload",
        data={
            "name": name,
            "activate": str(activate).lower(),
            "file": (BytesIO(content.encode("utf-8")), f"{name}.csv"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    return response.get_json()["dataset"]


def _build(client, headers, dataset_ids, **overrides):
    payload = {
        "dataset_ids": dataset_ids,
        "embedding_space": "shared-pca-v1",
        "confirm_shared_space": True,
        "index_type": "flat",
        "metric": "l2",
        **overrides,
    }
    return client.post("/api/federated/index", json=payload, headers=headers)


def test_joint_index_returns_cross_dataset_results_with_source_identity(client):
    headers = _headers(client)
    first = _csv_upload(
        client,
        headers,
        "study-a",
        [("a0", "T", 0, 0), ("a1", "T", 10, 10)],
    )
    second = _csv_upload(
        client,
        headers,
        "study-b",
        [("b0", "B", 0.1, 0), ("b1", "B", 5, 5)],
    )

    built = _build(client, headers, [second["id"], first["id"]])
    searched = client.post(
        "/api/federated/search",
        json={"query_dataset_id": first["id"], "cell_id": 0, "top_k": 3},
        headers=headers,
    )

    assert built.status_code == 200
    status = built.get_json()
    assert status["ready"] is True
    assert status["dataset_ids"] == sorted([first["id"], second["id"]])
    assert status["n_cells"] == 4
    assert status["compatibility"] == {
        "dimension_verified": True,
        "shared_space_asserted": True,
    }
    assert searched.status_code == 200
    body = searched.get_json()
    assert body["query"]["cell_name"] == "a0"
    assert body["results"][0] == {
        "global_cell_id": 2,
        "composite_id": f"{second['id']}:0",
        "dataset_id": second["id"],
        "dataset": "study-b",
        "cell_id": 0,
        "cell_name": "b0",
        "cell_type": "B",
        "distance": pytest.approx(0.01),
    }
    assert body["cross_dataset_returned"] == 2
    assert all(row["composite_id"] != f"{first['id']}:0" for row in body["results"])


def test_joint_filter_is_exact_across_source_datasets(client):
    headers = _headers(client)
    first = _csv_upload(
        client,
        headers,
        "filter-a",
        [("a0", "T", 0, 0), ("a1", "B", 8, 8)],
    )
    second = _csv_upload(
        client,
        headers,
        "filter-b",
        [("b0", "B", 0.2, 0), ("b1", "T", 0.1, 0)],
    )
    _build(client, headers, [first["id"], second["id"]])

    response = client.post(
        "/api/federated/search",
        json={
            "query_dataset_id": first["id"],
            "cell_id": 0,
            "top_k": 5,
            "cell_type": "B",
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["filter_strategy"] == "exact_federated_subset"
    assert [row["cell_name"] for row in body["results"]] == ["b0", "a1"]
    assert all(row["cell_type"] == "B" for row in body["results"])


def test_incompatible_build_is_rejected_without_replacing_published_collection(client):
    headers = _headers(client)
    first = _csv_upload(client, headers, "stable-a", [("a0", "T", 0, 0)])
    second = _csv_upload(client, headers, "stable-b", [("b0", "T", 1, 1)])
    built = _build(client, headers, [first["id"], second["id"]]).get_json()

    content = b"cell_id,x,y,z\nc0,0,0,0\n"
    third_response = client.post(
        "/api/datasets/upload",
        data={
            "name": "wrong-dim",
            "activate": "false",
            "file": (BytesIO(content), "wrong.csv"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    third = third_response.get_json()["dataset"]
    rejected = _build(client, headers, [first["id"], third["id"]])
    after = client.get("/api/federated/index/status", headers=headers).get_json()

    assert rejected.status_code == 400
    assert "维度不一致" in rejected.get_json()["error"]
    assert after["collection_fingerprint"] == built["collection_fingerprint"]
    assert after["dataset_ids"] == built["dataset_ids"]


@pytest.mark.parametrize(
    "payload,error",
    [
        ({"dataset_ids": [1, 2]}, "embedding_space"),
        (
            {"dataset_ids": [1, 2], "embedding_space": "space"},
            "确认",
        ),
        (
            {
                "dataset_ids": [1, 1],
                "embedding_space": "space",
                "confirm_shared_space": True,
            },
            "不能重复",
        ),
    ],
)
def test_joint_build_requires_explicit_shared_space_contract(client, payload, error):
    response = client.post("/api/federated/index", json=payload, headers=_headers(client))

    assert response.status_code == 400
    assert error in response.get_json()["error"]


def test_deleting_a_member_invalidates_the_published_joint_index(client):
    headers = _headers(client)
    first = _csv_upload(client, headers, "delete-a", [("a0", "T", 0, 0)])
    second = _csv_upload(client, headers, "delete-b", [("b0", "T", 1, 1)])
    _build(client, headers, [first["id"], second["id"]])

    deleted = client.delete(f"/api/datasets/{second['id']}", headers=headers)
    status = client.get("/api/federated/index/status", headers=headers)
    searched = client.post(
        "/api/federated/search",
        json={"query_dataset_id": first["id"], "cell_id": 0, "top_k": 1},
        headers=headers,
    )

    assert deleted.status_code == 200
    assert status.get_json()["ready"] is False
    assert searched.status_code == 400
    assert "尚未构建" in searched.get_json()["error"]


def test_federated_endpoints_require_authentication(client):
    assert client.get("/api/federated/index/status").status_code == 401
    assert client.post("/api/federated/index", json={}).status_code == 401
    assert client.post("/api/federated/search", json={}).status_code == 401
