"""全局配置。

通过环境变量覆盖，便于区分开发 / 生产。
"""

import os
import tempfile
from pathlib import Path

# 项目根目录: backend/
BASE_DIR = Path(__file__).resolve().parents[2]
# 数据集目录: <repo>/data
DATA_DIR = BASE_DIR.parent / "data"
# 索引产物目录
INDEX_DIR = BASE_DIR / "indices"
LOG_DIR = BASE_DIR / "logs"

DEVELOPMENT_SECRET = "scann-development-secret-key-change-before-production"
EXAMPLE_SECRET = "replace-with-at-least-32-random-characters"
EXAMPLE_ADMIN_PASSWORD = "replace-with-a-strong-bootstrap-password"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


class Config:
    ENVIRONMENT = os.environ.get("SCANN_ENV", "development").strip().lower()
    SECRET_KEY = os.environ.get("SCANN_SECRET_KEY", DEVELOPMENT_SECRET)
    DEBUG = _env_bool("SCANN_DEBUG", False)

    DATA_DIR = str(DATA_DIR)
    INDEX_DIR = str(INDEX_DIR)
    LOG_DIR = str(LOG_DIR)
    LOG_TO_FILE = _env_bool("SCANN_LOG_TO_FILE", True)
    LOG_LEVEL = os.environ.get("SCANN_LOG_LEVEL", "INFO").upper()
    MAX_CONTENT_LENGTH = int(os.environ.get("SCANN_MAX_UPLOAD_BYTES", 512 * 1024 * 1024))

    CORS_ORIGINS = _env_csv(
        "SCANN_CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    )
    HOST = os.environ.get("SCANN_HOST", "127.0.0.1")
    PORT = int(os.environ.get("SCANN_PORT", 5000))

    ADMIN_USERNAME = os.environ.get("SCANN_ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("SCANN_ADMIN_PASSWORD", "admin123")

    # 演示数据规模（无真实 .h5ad 时用于生成假向量）
    DEMO_N_CELLS = int(os.environ.get("SCANN_DEMO_N_CELLS", 2000))
    DEMO_DIM = int(os.environ.get("SCANN_DEMO_DIM", 50))

    # SQLite 数据库
    SQLALCHEMY_DATABASE_URI = os.environ.get("SCANN_DB_URI", f"sqlite:///{BASE_DIR / 'scann.db'}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 默认检索参数
    DEFAULT_INDEX_TYPE = os.environ.get("SCANN_DEFAULT_INDEX", "flat")  # flat | faiss
    DEFAULT_METRIC = os.environ.get("SCANN_DEFAULT_METRIC", "l2")
    DEFAULT_TOP_K = 10
    MAX_TOP_K = int(os.environ.get("SCANN_MAX_TOP_K", 1000))
    MAX_EVAL_QUERIES = int(os.environ.get("SCANN_MAX_EVAL_QUERIES", 1000))
    MAX_VISUALIZATION_POINTS = int(os.environ.get("SCANN_MAX_VISUALIZATION_POINTS", 3000))
    NUMBA_CACHE_DIR = os.environ.get(
        "SCANN_NUMBA_CACHE_DIR",
        str(
            Path(tempfile.gettempdir())
            / f"scann-numba-cache-{getattr(os, 'getuid', lambda: 'default')()}"
        ),
    )
    NUMBA_NUM_THREADS = int(os.environ.get("SCANN_NUMBA_NUM_THREADS", 1))
