"""scANN 后端入口。

运行：
    python run.py
默认监听 http://127.0.0.1:5000
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host=app.config["HOST"],
        port=app.config["PORT"],
        debug=app.config["DEBUG"],
    )
