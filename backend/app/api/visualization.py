"""Authenticated 2D embedding endpoint for query-result visualization."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.core.security import require_auth
from app.services.projection import projection_service

bp = Blueprint("visualization", __name__, url_prefix="/api/visualization")


@bp.get("/embedding")
@require_auth
def embedding():
    try:
        max_points = _parse_int(request.args.get("max_points", 1200), "max_points")
        configured_limit = current_app.config["MAX_VISUALIZATION_POINTS"]
        if not 10 <= max_points <= configured_limit:
            raise ValueError(f"max_points 必须在 10 到 {configured_limit} 之间")
        method = request.args.get("method", "umap").strip().lower()
        if method not in {"umap", "pca"}:
            raise ValueError("method 仅支持 umap 或 pca")
        include_ids = _parse_ids(request.args.get("include_ids", ""))
        return jsonify(projection_service.project(max_points, include_ids, method))
    except (TypeError, ValueError, RuntimeError) as exc:
        return jsonify(error=str(exc)), 400


def _parse_int(value, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} 必须是整数")
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} 必须是整数") from exc


def _parse_ids(value: str) -> list[int]:
    if not value:
        return []
    values = value.split(",")
    if len(values) > 101:
        raise ValueError("include_ids 最多包含 101 个细胞编号")
    try:
        parsed = [int(item) for item in values]
    except ValueError as exc:
        raise ValueError("include_ids 必须是逗号分隔的整数") from exc
    return list(dict.fromkeys(parsed))
