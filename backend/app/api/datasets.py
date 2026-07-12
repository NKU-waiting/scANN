"""数据管理 API。

GET  /api/datasets            列出可用数据集
POST /api/datasets/load       加载数据集（demo 或 data 目录下的 .h5ad 文件）
DELETE /api/datasets/<name>   删除数据集 —— 预留（结项要求：动态数据集管理）
"""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, request

from app.core.config import Config
from app.core.security import require_admin, require_auth
from app.services.data_loader import load_h5ad
from app.services.search import search_service

bp = Blueprint("datasets", __name__, url_prefix="/api/datasets")


@bp.get("")
@require_auth
def list_datasets():
    search_service.ensure_initialized()
    current = search_service.dataset
    return jsonify(datasets=[{
        "name": current.name,
        "n_cells": current.n_cells,
        "dim": current.dim,
        "active": True,
    }] if current else [])


@bp.post("/load")
@require_auth
def load_dataset():
    """加载数据集。默认 demo；传 path 则加载 data 目录下的 .h5ad 文件。"""
    data = request.get_json(silent=True) or {}
    path = data.get("path")
    if not path:
        search_service.load_demo()
        return jsonify(search_service.status())

    try:
        dataset_path = _resolve_h5ad_path(path)
        use_obsm = _parse_use_obsm(data)
        dataset = load_h5ad(str(dataset_path), use_obsm=use_obsm)
        return jsonify(search_service.set_dataset(dataset))
    except (OSError, ValueError) as e:
        return jsonify(error=str(e)), 400


@bp.delete("/<name>")
@require_admin
def delete_dataset(name: str):
    # TODO: 结项要求 —— 支持数据集删除与动态索引管理
    return jsonify(error="数据集删除尚未实现（骨架）"), 501


def _resolve_h5ad_path(raw_path) -> Path:
    if not isinstance(raw_path, str):
        raise ValueError("path 必须是字符串")

    path_text = raw_path.strip()
    if not path_text:
        raise ValueError("path 不能为空")

    requested = Path(path_text)
    if requested.is_absolute():
        raise ValueError("path 只能指向 data 目录内的相对路径")
    if ".." in requested.parts:
        raise ValueError("path 不能包含目录穿越片段")

    if requested.parts and requested.parts[0] == "data":
        requested = Path(*requested.parts[1:])

    if not requested.name:
        raise ValueError("path 必须指向 .h5ad 文件")
    if requested.suffix.lower() != ".h5ad":
        raise ValueError("path 必须指向 .h5ad 文件")

    data_dir = Path(Config.DATA_DIR).resolve()
    dataset_path = (data_dir / requested).resolve()
    try:
        dataset_path.relative_to(data_dir)
    except ValueError as exc:
        raise ValueError("path 只能指向 data 目录内的文件") from exc

    if not dataset_path.is_file():
        raise ValueError(f"数据文件不存在: {requested.as_posix()}")

    return dataset_path


def _parse_use_obsm(data: dict) -> str | None:
    if "use_obsm" not in data:
        return "X_pca"
    use_obsm = data["use_obsm"]
    if use_obsm is None:
        return None
    if not isinstance(use_obsm, str):
        raise ValueError("use_obsm 必须是字符串或 null")
    use_obsm = use_obsm.strip()
    return use_obsm or None
