"""数据管理 API（骨架）。

GET  /api/datasets            列出可用数据集
POST /api/datasets/load       加载数据集（demo 或指定 .h5ad 路径）—— 预留
DELETE /api/datasets/<name>   删除数据集 —— 预留（结项要求：动态数据集管理）
"""
from flask import Blueprint, jsonify, request

from app.services.search import search_service

bp = Blueprint("datasets", __name__, url_prefix="/api/datasets")


@bp.get("")
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
def load_dataset():
    """加载数据集。默认 demo；传 path 则加载 .h5ad（待实现真实预处理）。"""
    data = request.get_json(silent=True) or {}
    path = data.get("path")
    if not path:
        search_service.load_demo()
        return jsonify(search_service.status())
    # TODO: 调用 data_loader.load_h5ad(path) 并 set_dataset，串接预处理流程
    return jsonify(error="加载 .h5ad 尚未实现（骨架）"), 501


@bp.delete("/<name>")
def delete_dataset(name: str):
    # TODO: 结项要求 —— 支持数据集删除与动态索引管理
    return jsonify(error="数据集删除尚未实现（骨架）"), 501
