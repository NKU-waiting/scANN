"""索引构建 API。

POST /api/index/build   {"index_type": "faiss", "metric": "l2"}
GET  /api/index/status
"""
from flask import Blueprint, jsonify, request

from app.services.search import search_service

bp = Blueprint("index", __name__, url_prefix="/api/index")


@bp.post("/build")
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
def status():
    search_service.ensure_initialized()
    return jsonify(search_service.status())
