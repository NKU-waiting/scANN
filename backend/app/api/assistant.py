"""Authenticated grounded natural-language cell-analysis API."""

from flask import Blueprint, jsonify, request

from app.core.security import require_auth
from app.services.assistant import AssistantProviderError, assistant_service
from app.services.datasets import DatasetNotFoundError

bp = Blueprint("assistant", __name__, url_prefix="/api/assistant")


@bp.get("/status")
@require_auth
def status():
    return jsonify(assistant_service.status())


@bp.post("/query")
@require_auth
def query():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="请求体必须是 JSON 对象"), 400
    try:
        result = assistant_service.answer(data)
    except DatasetNotFoundError as exc:
        return jsonify(error=str(exc)), 404
    except AssistantProviderError as exc:
        return jsonify(error=str(exc)), 502
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(result)
