"""应用工厂。

`create_app()` 负责装配配置、跨域、蓝图，并初始化检索服务单例。
"""

from flask import Flask, jsonify
from flask_cors import CORS

from app.api import register_blueprints
from app.core.config import Config
from app.core.extensions import db
from app.core.runtime import configure_runtime


def create_app(config: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config)

    configure_runtime(app)
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    db.init_app(app)

    # 导入模型使 SQLAlchemy 感知表结构，再建表；播种默认 admin
    with app.app_context():
        from app.models import User  # noqa: F401

        db.create_all()
        if not User.query.filter_by(role="admin").first():
            admin = User(username=app.config["ADMIN_USERNAME"], role="admin")
            admin.set_password(app.config["ADMIN_PASSWORD"])
            db.session.add(admin)
            db.session.commit()

        from app.services.datasets import dataset_service

        try:
            dataset_service.restore_active()
        except (OSError, ValueError, RuntimeError):
            app.logger.exception("Failed to restore the previously active dataset")

    register_blueprints(app)

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", service="scANN", version="1.0.0")

    return app
