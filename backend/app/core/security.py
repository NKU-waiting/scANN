"""JWT authentication backed by the current database user record."""

from __future__ import annotations

import functools
import hmac

import jwt
from flask import current_app, g, jsonify, request


def _load_current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or not auth[7:].strip():
        return None, (jsonify(error="缺少或格式错误的 Authorization 头"), 401)

    try:
        payload = jwt.decode(
            auth[7:].strip(),
            current_app.config["SECRET_KEY"],
            algorithms=["HS256"],
            issuer="scann",
            options={"require": ["exp", "iat", "iss", "sub", "ver"]},
        )
        user_id = int(payload["sub"])
    except jwt.ExpiredSignatureError:
        return None, (jsonify(error="token 已过期"), 401)
    except (KeyError, TypeError, ValueError, jwt.InvalidTokenError):
        return None, (jsonify(error="无效 token"), 401)

    from app.core.extensions import db
    from app.models import User

    user = db.session.get(User, user_id)
    if user is None:
        return None, (jsonify(error="用户不存在或登录已失效"), 401)
    if not hmac.compare_digest(str(payload["ver"]), user.token_version()):
        return None, (jsonify(error="用户身份已变更，请重新登录"), 401)
    return user, None


def require_auth(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        user, error = _load_current_user()
        if error:
            return error
        g.current_user = user
        return view(*args, **kwargs)

    return wrapper


def require_admin(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        user, error = _load_current_user()
        if error:
            return error
        if user.role != "admin":
            return jsonify(error="需要管理员权限"), 403
        g.current_user = user
        return view(*args, **kwargs)

    return wrapper
