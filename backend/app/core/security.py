"""JWT 鉴权装饰器。"""
import functools

import jwt
from flask import current_app, g, jsonify, request


def _decode_token():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None, (jsonify(error="缺少或格式错误的 Authorization 头"), 401)
    token = auth[7:]
    try:
        payload = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None, (jsonify(error="token 已过期"), 401)
    except jwt.InvalidTokenError:
        return None, (jsonify(error="无效 token"), 401)
    return payload, None


def require_auth(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        payload, err = _decode_token()
        if err:
            return err
        g.current_user = payload
        return f(*args, **kwargs)
    return wrapper


def require_admin(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        payload, err = _decode_token()
        if err:
            return err
        if payload.get("role") != "admin":
            return jsonify(error="需要管理员权限"), 403
        g.current_user = payload
        return f(*args, **kwargs)
    return wrapper
