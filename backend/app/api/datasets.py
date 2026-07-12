"""Managed dataset upload, activation, listing, import, and deletion APIs."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.core.security import require_admin, require_auth
from app.services.datasets import (
    ActiveDatasetError,
    DatasetConflictError,
    DatasetNotFoundError,
    dataset_service,
)

bp = Blueprint("datasets", __name__, url_prefix="/api/datasets")


@bp.get("")
@require_auth
def list_datasets():
    return jsonify(datasets=dataset_service.list_resources())


@bp.post("/upload")
@require_auth
def upload_dataset():
    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify(error="必须通过 file 字段上传数据文件"), 400
    try:
        use_obsm = _parse_use_obsm(request.form.get("use_obsm", "X_pca"))
        activate = _parse_bool(request.form.get("activate", "true"), "activate")
        result = dataset_service.upload(
            uploaded=uploaded,
            name=request.form.get("name"),
            owner_id=g.current_user.id,
            use_obsm=use_obsm,
            activate=activate,
        )
    except DatasetConflictError as exc:
        return jsonify(error=str(exc)), 409
    except (OSError, ValueError) as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(result), 201


@bp.post("/<int:dataset_id>/activate")
@require_auth
def activate_dataset(dataset_id: int):
    try:
        return jsonify(dataset_service.activate(dataset_id))
    except DatasetNotFoundError as exc:
        return jsonify(error=str(exc)), 404
    except (OSError, ValueError, RuntimeError) as exc:
        return jsonify(error=str(exc)), 400


@bp.post("/demo/activate")
@require_auth
def activate_demo():
    return jsonify(dataset_service.activate_demo())


@bp.post("/load")
@require_auth
def load_dataset():
    """Compatibility entrypoint for demo, managed IDs, or safe server-side imports."""
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify(error="请求体必须是 JSON 对象"), 400
    try:
        if data.get("dataset_id") is not None:
            dataset_id = _parse_positive_int(data["dataset_id"], "dataset_id")
            return jsonify(dataset_service.activate(dataset_id))
        if data.get("path") is not None:
            result = dataset_service.import_existing(
                raw_path=data["path"],
                name=data.get("name"),
                owner_id=g.current_user.id,
                use_obsm=_parse_use_obsm(data.get("use_obsm", "X_pca")),
                activate=_parse_bool(data.get("activate", True), "activate"),
            )
            return jsonify(result), 201
        return jsonify(dataset_service.activate_demo())
    except DatasetConflictError as exc:
        return jsonify(error=str(exc)), 409
    except DatasetNotFoundError as exc:
        return jsonify(error=str(exc)), 404
    except (OSError, ValueError, RuntimeError) as exc:
        return jsonify(error=str(exc)), 400


@bp.delete("/<int:dataset_id>")
@require_admin
def delete_dataset(dataset_id: int):
    try:
        return jsonify(dataset_service.delete(dataset_id))
    except DatasetNotFoundError as exc:
        return jsonify(error=str(exc)), 404
    except ActiveDatasetError as exc:
        return jsonify(error=str(exc)), 409
    except (OSError, ValueError) as exc:
        return jsonify(error=str(exc)), 400


def _parse_use_obsm(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("use_obsm 必须是字符串或 null")
    normalized = value.strip()
    if normalized.lower() in {"", "none", "null", "x"}:
        return None
    if len(normalized) > 100:
        raise ValueError("use_obsm 不能超过 100 个字符")
    return normalized


def _parse_bool(value, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"{field} 必须是布尔值")


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
