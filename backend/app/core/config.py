"""全局配置。

通过环境变量覆盖，便于区分开发 / 生产。
"""
import os
from pathlib import Path

# 项目根目录: backend/
BASE_DIR = Path(__file__).resolve().parents[2]
# 数据集目录: <repo>/data
DATA_DIR = BASE_DIR.parent / "data"
# 索引产物目录
INDEX_DIR = BASE_DIR / "indices"


class Config:
    SECRET_KEY = os.environ.get("SCANN_SECRET_KEY", "dev-secret-change-me")

    DATA_DIR = str(DATA_DIR)
    INDEX_DIR = str(INDEX_DIR)

    # 演示数据规模（无真实 .h5ad 时用于生成假向量）
    DEMO_N_CELLS = int(os.environ.get("SCANN_DEMO_N_CELLS", 2000))
    DEMO_DIM = int(os.environ.get("SCANN_DEMO_DIM", 50))

    # SQLite 数据库
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "SCANN_DB_URI",
        f"sqlite:///{BASE_DIR / 'scann.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 默认检索参数
    DEFAULT_INDEX_TYPE = os.environ.get("SCANN_DEFAULT_INDEX", "flat")  # flat | faiss
    DEFAULT_METRIC = os.environ.get("SCANN_DEFAULT_METRIC", "l2")
    DEFAULT_TOP_K = 10
    MAX_TOP_K = int(os.environ.get("SCANN_MAX_TOP_K", 1000))
    MAX_EVAL_QUERIES = int(os.environ.get("SCANN_MAX_EVAL_QUERIES", 1000))
