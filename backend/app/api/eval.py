"""性能评测 API。

POST /api/eval   评测一组 ANN 索引相对精确检索的召回率与查询耗时。
"""

from flask import Blueprint, current_app, g, jsonify, request

from app.core.config import Config
from app.core.security import require_auth
from app.services.eval import evaluate_index
from app.services.history import history_service
from app.services.index import VALID_INDEX_TYPES, VALID_METRICS
from app.services.search import search_service

bp = Blueprint("eval", __name__, url_prefix="/api")


@bp.post("/eval")
@require_auth
def evaluate():
    try:
        data = request.get_json(silent=True)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")

        index_types = data.get("index_types", ["flat"])
        if not isinstance(index_types, list) or not index_types:
            raise ValueError("index_types 必须是非空数组")
        if any(not isinstance(item, str) for item in index_types):
            raise ValueError("index_types 中的值必须是字符串")
        index_types = [item.strip().lower() for item in index_types]
        invalid = [item for item in index_types if item not in VALID_INDEX_TYPES]
        if invalid:
            raise ValueError(f"不支持的索引类型: {invalid}")

        top_k = _parse_positive_int(data.get("top_k", Config.DEFAULT_TOP_K), "top_k")
        n_queries = _parse_positive_int(data.get("n_queries", 100), "n_queries")
        max_top_k = current_app.config["MAX_TOP_K"]
        max_eval_queries = current_app.config["MAX_EVAL_QUERIES"]
        if top_k > max_top_k:
            raise ValueError(f"top_k 不能超过 {max_top_k}")
        if n_queries > max_eval_queries:
            raise ValueError(f"n_queries 不能超过 {max_eval_queries}")

        metric = data.get("metric", Config.DEFAULT_METRIC)
        if not isinstance(metric, str) or metric.lower() not in VALID_METRICS:
            raise ValueError(f"metric 仅支持 {', '.join(sorted(VALID_METRICS))}")
        metric = metric.lower()

        search_service.ensure_initialized()
        dataset = search_service.dataset
        results = []
        for index_type in index_types:
            result = evaluate_index(
                dataset=dataset,
                index_type=index_type,
                top_k=top_k,
                n_queries=n_queries,
                metric=metric,
            )
            results.append(result)
        log = history_service.record_evaluation(
            user_id=g.current_user.id,
            dataset=dataset,
            top_k=top_k,
            n_queries=results[0]["n_queries"],
            metric=metric,
            index_types=index_types,
            results=results,
        )
    except (TypeError, ValueError, RuntimeError) as exc:
        return jsonify(error=str(exc)), 400

    return jsonify(
        results=results,
        dataset=dataset.name,
        n_cells=dataset.n_cells,
        top_k=top_k,
        n_queries=results[0]["n_queries"],
        metric=metric,
        evaluation_id=log.id,
    )


def _parse_positive_int(value, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} 必须是正整数")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field} 必须是正整数")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} 必须是正整数") from exc
    if result < 1:
        raise ValueError(f"{field} 必须是正整数")
    return result
