"""Authenticated joint-index construction and cross-dataset search APIs."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.core.config import Config
from app.core.security import require_auth
from app.services.datasets import DatasetNotFoundError
from app.services.federated import federated_search_service
from app.services.index import VALID_INDEX_TYPES, VALID_METRICS

bp = Blueprint("federated", __name__, url_prefix="/api/federated")


@bp.get("/index/status")
@require_auth
def status():
    return jsonify(federated_search_service.status())


@bp.post("/index")
@require_auth
def build_index():
    try:
        data = _json_object()
        dataset_ids = _dataset_ids(data.get("dataset_ids"))
        embedding_space = _nonempty_string(data.get("embedding_space"), "embedding_space", 100)
        if data.get("confirm_shared_space") is not True:
            raise ValueError("必须确认所选数据集已映射到同一向量空间")
        index_type = _choice(data.get("index_type", "hnsw"), "index_type", VALID_INDEX_TYPES)
        metric = _choice(data.get("metric", Config.DEFAULT_METRIC), "metric", VALID_METRICS)
        result = federated_search_service.build(dataset_ids, embedding_space, index_type, metric)
    except DatasetNotFoundError as exc:
        return jsonify(error=str(exc)), 404
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(result)


@bp.post("/search")
@require_auth
def search():
    try:
        data = _json_object()
        top_k = _positive_int(data.get("top_k", Config.DEFAULT_TOP_K), "top_k")
        cell_type = data.get("cell_type")
        if cell_type is not None:
            cell_type = _nonempty_string(cell_type, "cell_type", 200)

        has_vector = data.get("vector") is not None
        has_cell = data.get("cell_id") is not None or data.get("query_dataset_id") is not None
        if has_vector == has_cell:
            raise ValueError("需且只能提供 vector，或 query_dataset_id + cell_id")
        if has_vector:
            result = federated_search_service.search_by_vector(data["vector"], top_k, cell_type)
        else:
            if data.get("query_dataset_id") is None or data.get("cell_id") is None:
                raise ValueError("query_dataset_id 和 cell_id 必须同时提供")
            result = federated_search_service.search_by_cell(
                _positive_int(data["query_dataset_id"], "query_dataset_id"),
                _nonnegative_int(data["cell_id"], "cell_id"),
                top_k,
                cell_type,
            )
    except (TypeError, ValueError, RuntimeError) as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(result)


def _json_object() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("请求体必须是 JSON 对象")
    return data


def _dataset_ids(value) -> list[int]:
    if not isinstance(value, list) or len(value) < 2:
        raise ValueError("dataset_ids 必须是至少包含 2 项的数组")
    parsed = [_positive_int(item, "dataset_ids") for item in value]
    if len(set(parsed)) != len(parsed):
        raise ValueError("dataset_ids 不能重复")
    return parsed


def _positive_int(value, field: str) -> int:
    parsed = _nonnegative_int(value, field)
    if parsed < 1:
        raise ValueError(f"{field} 必须是正整数")
    return parsed


def _nonnegative_int(value, field: str) -> int:
    if isinstance(value, bool) or isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field} 必须是非负整数")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} 必须是非负整数") from exc
    if parsed < 0:
        raise ValueError(f"{field} 必须是非负整数")
    return parsed


def _nonempty_string(value, field: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是非空字符串")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{field} 不能超过 {max_length} 个字符")
    return normalized


def _choice(value, field: str, choices: set[str] | frozenset[str]) -> str:
    normalized = _nonempty_string(value, field, 30).lower()
    if normalized not in choices:
        raise ValueError(f"{field} 仅支持 {', '.join(sorted(choices))}")
    return normalized
