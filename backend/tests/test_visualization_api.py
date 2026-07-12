"""Regression tests for deterministic PCA and UMAP visualization endpoints."""
from __future__ import annotations

import math

import pytest

from app import create_app
from app.core.config import Config
from app.services.search import search_service


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret-key-with-at-least-thirty-two-bytes"
    LOG_TO_FILE = False
    DEMO_N_CELLS = 60
    DEMO_DIM = 6
    MAX_VISUALIZATION_POINTS = 100


@pytest.fixture()
def client():
    search_service.reset()
    app = create_app(TestConfig)
    with app.test_client() as test_client:
        login = test_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        test_client.environ_base["HTTP_AUTHORIZATION"] = (
            f"Bearer {login.get_json()['token']}"
        )
        yield test_client
    search_service.reset()


def test_pca_projection_samples_and_forces_requested_ids(client):
    response = client.get(
        "/api/visualization/embedding?method=pca&max_points=10&include_ids=0,59"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["method"] == "pca"
    assert payload["sampled"] == 10
    assert payload["returned"] >= 10
    ids = {point["cell_id"] for point in payload["points"]}
    assert {0, 59} <= ids
    assert all(
        math.isfinite(point["x"]) and math.isfinite(point["y"])
        for point in payload["points"]
    )


def test_umap_projection_is_reproducible_from_cache(client):
    first = client.get("/api/visualization/embedding?method=umap&max_points=30")
    second = client.get("/api/visualization/embedding?method=umap&max_points=30")

    assert first.status_code == 200
    assert first.get_json()["method"] == "umap"
    assert first.get_json()["points"] == second.get_json()["points"]


@pytest.mark.parametrize(
    "query",
    [
        "method=tsne&max_points=20",
        "method=pca&max_points=2",
        "method=pca&max_points=200",
        "method=pca&max_points=20&include_ids=999",
        "method=pca&max_points=20&include_ids=a,b",
    ],
)
def test_projection_rejects_invalid_parameters(client, query):
    response = client.get(f"/api/visualization/embedding?{query}")

    assert response.status_code == 400
