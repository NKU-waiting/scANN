"""性能评测 API（骨架）。

POST /api/eval   评测 ANN 索引相对精确检索的召回率与查询耗时。
结项要求：实验评估（响应时间等）。
"""
from flask import Blueprint, jsonify, request

bp = Blueprint("eval", __name__, url_prefix="/api")


@bp.post("/eval")
def evaluate():
    data = request.get_json(silent=True) or {}
    # TODO: 以 FlatIndex 结果为 ground truth，
    #       对比目标 index_type 的 recall@k 与平均 query_ms。
    return jsonify(
        error="性能评测尚未实现（骨架）",
        hint="计划: 抽样查询 → flat 作为 ground truth → 计算 recall@k 与平均查询耗时",
        echo=data,
    ), 501
