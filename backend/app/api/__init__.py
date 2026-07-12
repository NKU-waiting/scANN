"""API 蓝图注册。"""
from flask import Flask

from .auth import bp as auth_bp
from .datasets import bp as datasets_bp
from .index import bp as index_bp
from .search import bp as search_bp
from .visualization import bp as visualization_bp
from .eval import bp as eval_bp
from .history import bp as history_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(auth_bp)
    app.register_blueprint(datasets_bp)
    app.register_blueprint(index_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(eval_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(visualization_bp)
