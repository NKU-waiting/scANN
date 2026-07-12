"""Authenticated query and evaluation history APIs."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.core.security import require_auth
from app.services.history import history_service

bp = Blueprint("history", __name__, url_prefix="/api/history")


@bp.get("/queries")
@require_auth
def query_history():
    try:
        limit = _parse_limit(request.args.get("limit", 30))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    records = history_service.list_queries(
        g.current_user.id,
        g.current_user.role == "admin",
        limit,
    )
    return jsonify(queries=records)


@bp.get("/evaluations")
@require_auth
def evaluation_history():
    try:
        limit = _parse_limit(request.args.get("limit", 20))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    records = history_service.list_evaluations(
        g.current_user.id,
        g.current_user.role == "admin",
        limit,
    )
    return jsonify(evaluations=records)


def _parse_limit(value) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("limit 必须是 1 到 100 的整数") from exc
    if isinstance(value, bool) or not 1 <= limit <= 100:
        raise ValueError("limit 必须是 1 到 100 的整数")
    return limit
