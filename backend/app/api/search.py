"""查询检索 API（核心）。

POST /api/search
请求体（二选一）：
    {"cell_id": 0, "top_k": 5, "index_type": "flat", "metric": "l2", "cell_type": "type_1"}
    {"vector": [...], "top_k": 5}
"""

from flask import Blueprint, g, jsonify, request

from app.core.config import Config
from app.core.security import require_auth
from app.services.history import history_service
from app.services.search import search_service

bp = Blueprint("search", __name__, url_prefix="/api")


@bp.post("/search")
@require_auth
def search():
    try:
        data = request.get_json(silent=True)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")

        top_k = _parse_int(data.get("top_k", Config.DEFAULT_TOP_K), "top_k")
        cell_type = data.get("cell_type")
        if cell_type is not None:
            if not isinstance(cell_type, str):
                raise ValueError("cell_type 必须是字符串")
            cell_type = cell_type.strip() or None

        has_vector = "vector" in data and data["vector"] is not None
        has_cell_id = "cell_id" in data and data["cell_id"] is not None
        if not has_vector and not has_cell_id:
            raise ValueError("需提供 cell_id 或 vector")
        if has_vector and has_cell_id:
            raise ValueError("cell_id 和 vector 只能提供一个")

        index_type = _parse_optional_string(data.get("index_type"), "index_type")
        metric = _parse_optional_string(data.get("metric"), "metric")
        if not has_vector:
            cell_id = _parse_int(data["cell_id"], "cell_id")
            data["cell_id"] = cell_id
        with search_service.lifecycle_lock():
            search_service.ensure_initialized()
            if (index_type and index_type != search_service.index_type) or (
                metric and metric != search_service.metric
            ):
                search_service.build_index(index_type, metric)

            if has_vector:
                result = search_service.search_by_vector(data["vector"], top_k, cell_type)
                result["query_cell_id"] = None
            else:
                result = search_service.search_by_cell(cell_id, top_k, cell_type)
                result["query_cell_id"] = cell_id
        data["top_k"] = top_k
        log = history_service.record_query(g.current_user.id, data, result)
        result["query_id"] = log.id
    except (TypeError, ValueError, RuntimeError) as exc:
        return jsonify(error=str(exc)), 400

    return jsonify(result)


def _parse_int(value, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} 必须是整数")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field} 必须是整数")
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} 必须是整数") from exc


def _parse_optional_string(value, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是非空字符串")
    return value.strip().lower()
