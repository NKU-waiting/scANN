"""性能评测 API。

POST /api/eval   评测一组 ANN 索引相对精确检索的召回率与查询耗时。
"""
from flask import Blueprint, jsonify, request

from app.core.config import Config
from app.services.eval import evaluate_index
from app.services.search import search_service

bp = Blueprint("eval", __name__, url_prefix="/api")

VALID_INDEX_TYPES = {"flat", "faiss", "ivf", "hnsw", "pq"}


@bp.post("/eval")
def evaluate():
    data = request.get_json(silent=True) or {}

    index_types = data.get("index_types", ["flat"])
    if not isinstance(index_types, list) or len(index_types) == 0:
        return jsonify(error="index_types 必须是非空数组"), 400

    invalid = [t for t in index_types if t not in VALID_INDEX_TYPES]
    if invalid:
        return jsonify(
            error=f"不支持的索引类型: {invalid}",
            valid_types=sorted(VALID_INDEX_TYPES),
        ), 400

    top_k = int(data.get("top_k", Config.DEFAULT_TOP_K))
    n_queries = int(data.get("n_queries", 100))
    metric = data.get("metric", Config.DEFAULT_METRIC)

    if metric not in ("l2", "ip"):
        return jsonify(error="metric 仅支持 'l2' 或 'ip'"), 400
    if top_k < 1:
        return jsonify(error="top_k 必须 >= 1"), 400
    if n_queries < 1:
        return jsonify(error="n_queries 必须 >= 1"), 400

    search_service.ensure_initialized()
    dataset = search_service.dataset

    results = []
    for index_type in index_types:
        try:
            result = evaluate_index(
                dataset=dataset,
                index_type=index_type,
                top_k=top_k,
                n_queries=n_queries,
                metric=metric,
            )
        except Exception as e:
            return jsonify(error=f"评测 {index_type} 时出错: {e}"), 500
        results.append(result)

    return jsonify(
        results=results,
        dataset=dataset.name,
        n_cells=dataset.n_cells,
        top_k=top_k,
        n_queries=n_queries,
        metric=metric,
    )
