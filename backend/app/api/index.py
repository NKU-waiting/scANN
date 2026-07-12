"""Index build, status, persistence, loading, listing, and deletion APIs.

POST /api/index/build   {"index_type": "faiss", "metric": "l2"}
GET  /api/index/status
"""
from flask import Blueprint, g, jsonify, request

from app.core.security import require_admin, require_auth
from app.services.indexes import (
    ActiveIndexError,
    IncompatibleIndexError,
    IndexConflictError,
    IndexNotFoundError,
    index_artifact_service,
)
from app.services.search import search_service

bp = Blueprint("index", __name__, url_prefix="/api/index")


@bp.post("/build")
@require_auth
def build():
    try:
        data = request.get_json(silent=True)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")
        index_type = data.get("index_type")
        metric = data.get("metric")
        if index_type is not None and not isinstance(index_type, str):
            raise ValueError("index_type 必须是字符串")
        if metric is not None and not isinstance(metric, str):
            raise ValueError("metric 必须是字符串")
        search_service.ensure_initialized()
        info = search_service.build_index(index_type, metric)
    except (ValueError, RuntimeError) as e:
        return jsonify(error=str(e)), 400
    return jsonify(info)


@bp.get("/status")
@require_auth
def status():
    search_service.ensure_initialized()
    return jsonify(search_service.status())


@bp.get("/artifacts")
@require_auth
def list_artifacts():
    dataset_id = request.args.get("dataset_id")
    try:
        parsed_id = _parse_positive_int(dataset_id, "dataset_id") if dataset_id else None
        return jsonify(artifacts=index_artifact_service.list_artifacts(parsed_id))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@bp.post("/save")
@require_auth
def save_index():
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify(error="请求体必须是 JSON 对象"), 400
    try:
        result = index_artifact_service.save_current(data.get("name"), g.current_user.id)
    except IndexConflictError as exc:
        return jsonify(error=str(exc)), 409
    except (ValueError, RuntimeError) as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(result), 201


@bp.post("/load")
@require_auth
def load_index():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="请求体必须是 JSON 对象"), 400
    try:
        artifact_id = _parse_positive_int(data.get("index_id"), "index_id")
        return jsonify(index_artifact_service.load(artifact_id))
    except IndexNotFoundError as exc:
        return jsonify(error=str(exc)), 404
    except IncompatibleIndexError as exc:
        return jsonify(error=str(exc)), 409
    except (ValueError, RuntimeError) as exc:
        return jsonify(error=str(exc)), 400


@bp.delete("/artifacts/<int:artifact_id>")
@require_admin
def delete_index(artifact_id: int):
    try:
        return jsonify(index_artifact_service.delete(artifact_id))
    except IndexNotFoundError as exc:
        return jsonify(error=str(exc)), 404
    except ActiveIndexError as exc:
        return jsonify(error=str(exc)), 409
    except (ValueError, RuntimeError) as exc:
        return jsonify(error=str(exc)), 400


def _parse_positive_int(value, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} 必须是正整数")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} 必须是正整数") from exc
    if parsed < 1 or (isinstance(value, float) and not value.is_integer()):
        raise ValueError(f"{field} 必须是正整数")
    return parsed
