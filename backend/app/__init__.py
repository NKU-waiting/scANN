"""应用工厂。

`create_app()` 负责装配配置、跨域、蓝图，并初始化检索服务单例。
"""
from flask import Flask, jsonify
from flask_cors import CORS

from app.core.config import Config
from app.api import register_blueprints


def create_app(config: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config)

    # 前后端分离，允许前端开发服务器跨域访问 /api/*
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    register_blueprints(app)

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", service="scANN", version="0.1.0")

    return app
