"""scANN backend entrypoint with optional local ``.env`` loading."""

from dotenv import load_dotenv


def build_app():
    load_dotenv()
    from app import create_app

    return create_app()


app = build_app()

if __name__ == "__main__":
    app.run(
        host=app.config["HOST"],
        port=app.config["PORT"],
        debug=app.config["DEBUG"],
    )
