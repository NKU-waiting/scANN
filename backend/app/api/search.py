"""查询检索 API（核心）。

POST /api/search
请求体（二选一）：
    {"cell_id": 0, "top_k": 5, "index_type": "flat", "metric": "l2", "cell_type": "type_1"}
    {"vector": [...], "top_k": 5}
"""
from flask import Blueprint, jsonify, request

from app.core.config import Config
from app.services.search import search_service

bp = Blueprint("search", __name__, url_prefix="/api")


@bp.post("/search")
def search():
    data = request.get_json(silent=True) or {}
    top_k = int(data.get("top_k", Config.DEFAULT_TOP_K))
    cell_type = data.get("cell_type") or None

    # 如请求指定了索引类型/度量且与当前不同，则重建索引
    index_type = data.get("index_type")
    metric = data.get("metric")
    search_service.ensure_initialized()
    if (index_type and index_type != search_service.index_type) or \
       (metric and metric != search_service.metric):
        search_service.build_index(index_type, metric)

    try:
        if "vector" in data and data["vector"] is not None:
            result = search_service.search_by_vector(data["vector"], top_k, cell_type)
        elif "cell_id" in data and data["cell_id"] is not None:
            result = search_service.search_by_cell(int(data["cell_id"]), top_k, cell_type)
        else:
            return jsonify(error="需提供 cell_id 或 vector"), 400
    except (ValueError, RuntimeError) as e:
        return jsonify(error=str(e)), 400

    return jsonify(result)
