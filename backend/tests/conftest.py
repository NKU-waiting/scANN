"""Shared deterministic settings for backend regression tests."""
from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def single_threaded_faiss():
    """Avoid OpenMP startup overhead for the small deterministic test datasets."""
    try:
        import faiss
    except ImportError:
        yield
        return

    previous = faiss.omp_get_max_threads()
    faiss.omp_set_num_threads(1)
    try:
        yield
    finally:
        faiss.omp_set_num_threads(previous)
