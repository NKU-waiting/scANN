"""用户信息 API（骨架）。

POST /api/auth/register   用户注册 —— 预留
POST /api/auth/login      用户登录 —— 预留
管理员用户管理后续在此扩展。
"""
from flask import Blueprint, jsonify

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/register")
def register():
    # TODO: 接入用户模型与密码哈希
    return jsonify(error="注册尚未实现（骨架）"), 501


@bp.post("/login")
def login():
    # TODO: 校验凭证并签发会话 / JWT
    return jsonify(error="登录尚未实现（骨架）"), 501
