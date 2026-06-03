"""索引构建 API。

POST /api/index/build   {"index_type": "faiss", "metric": "l2"}
GET  /api/index/status
"""
from flask import Blueprint, jsonify, request

from app.services.search import search_service

bp = Blueprint("index", __name__, url_prefix="/api/index")


@bp.post("/build")
def build():
    data = request.get_json(silent=True) or {}
    search_service.ensure_initialized()
    try:
        info = search_service.build_index(data.get("index_type"), data.get("metric"))
    except (ValueError, RuntimeError) as e:
        return jsonify(error=str(e)), 400
    return jsonify(info)


@bp.get("/status")
def status():
    search_service.ensure_initialized()
    return jsonify(search_service.status())
