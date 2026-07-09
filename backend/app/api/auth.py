"""用户注册 / 登录 / 管理员用户管理 API。"""
from datetime import datetime, timedelta, timezone

import jwt
from flask import Blueprint, current_app, jsonify, request

from app.core.extensions import db
from app.core.security import require_admin
from app.models import User

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify(error="用户名和密码不能为空"), 400
    if len(username) > 64:
        return jsonify(error="用户名过长"), 400
    if len(password) < 6:
        return jsonify(error="密码至少 6 位"), 400

    if User.query.filter_by(username=username).first():
        return jsonify(error="用户名已存在"), 400

    user = User(username=username, role="user")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify(message="注册成功", user=user.to_dict()), 201


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify(error="用户名和密码不能为空"), 400

    user = User.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        return jsonify(error="用户名或密码错误"), 400

    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "exp": datetime.now(tz=timezone.utc) + timedelta(hours=24),
    }
    token = jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")
    return jsonify(token=token, user=user.to_dict())


@bp.get("/users")
@require_admin
def list_users():
    users = User.query.order_by(User.created_at).all()
    return jsonify(users=[u.to_dict() for u in users])


@bp.delete("/users/<int:user_id>")
@require_admin
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify(error="用户不存在"), 404
    db.session.delete(user)
    db.session.commit()
    return jsonify(message="删除成功")
