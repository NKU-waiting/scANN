"""Runtime validation, JSON errors, and privacy-conscious operational logging."""

from __future__ import annotations

import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

from app.core.config import DEVELOPMENT_SECRET, EXAMPLE_ADMIN_PASSWORD, EXAMPLE_SECRET
from app.core.extensions import db


def configure_runtime(app: Flask) -> None:
    """Validate deployment settings and install common runtime hooks."""
    _validate_config(app)
    _configure_numba(app)
    _configure_logging(app)

    @app.before_request
    def mark_request_start() -> None:
        g.request_started_at = time.perf_counter()

    @app.after_request
    def log_request(response):
        started_at = getattr(g, "request_started_at", None)
        elapsed_ms = (time.perf_counter() - started_at) * 1000 if started_at else 0.0
        app.logger.info(
            "%s %s %s %.2fms",
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        return jsonify(error=error.description, status=error.code), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        db.session.rollback()
        app.logger.exception("Unhandled request error: %s", type(error).__name__)
        return jsonify(error="服务器内部错误", status=500), 500


def _validate_config(app: Flask) -> None:
    numeric_bounds = {
        "MAX_CONTENT_LENGTH": 1,
        "DEMO_N_CELLS": 1,
        "DEMO_DIM": 1,
        "MAX_TOP_K": 1,
        "MAX_EVAL_QUERIES": 1,
        "MAX_VISUALIZATION_POINTS": 10,
        "NUMBA_NUM_THREADS": 1,
    }
    for name, minimum in numeric_bounds.items():
        value = app.config.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise RuntimeError(f"{name} 必须是不小于 {minimum} 的整数")

    if app.config["ENVIRONMENT"] != "production":
        return
    secret = app.config.get("SECRET_KEY", "")
    if secret in {DEVELOPMENT_SECRET, EXAMPLE_SECRET} or len(secret) < 32:
        raise RuntimeError("生产环境必须设置至少 32 字符的 SCANN_SECRET_KEY")
    admin_password = app.config.get("ADMIN_PASSWORD", "")
    if not admin_password or admin_password in {"admin123", EXAMPLE_ADMIN_PASSWORD}:
        raise RuntimeError("生产环境必须设置非默认 SCANN_ADMIN_PASSWORD")
    if app.config.get("DEBUG"):
        raise RuntimeError("生产环境不能启用 DEBUG")


def _configure_logging(app: Flask) -> None:
    level = getattr(logging, app.config.get("LOG_LEVEL", "INFO"), logging.INFO)
    app.logger.setLevel(level)
    if app.testing or not app.config.get("LOG_TO_FILE", True):
        return

    log_dir = Path(app.config["LOG_DIR"])
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "scann.log"
    if any(
        getattr(handler, "baseFilename", None) == str(log_path) for handler in app.logger.handlers
    ):
        return

    handler = RotatingFileHandler(log_path, maxBytes=2 * 1024 * 1024, backupCount=3)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    app.logger.addHandler(handler)


def _configure_numba(app: Flask) -> None:
    """Route UMAP's Numba cache to an explicitly writable runtime directory."""
    cache_dir = Path(app.config["NUMBA_CACHE_DIR"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    if not os.access(cache_dir, os.W_OK):
        raise RuntimeError("NUMBA_CACHE_DIR 不可写")
    os.environ["NUMBA_CACHE_DIR"] = str(cache_dir)
    os.environ["NUMBA_CACHE_LOCATOR_CLASSES"] = "UserProvidedCacheLocator"
    os.environ["NUMBA_NUM_THREADS"] = str(app.config["NUMBA_NUM_THREADS"])
