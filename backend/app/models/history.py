"""Durable query and evaluation run history without storing raw query vectors."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.extensions import db


class QueryLog(db.Model):
    __tablename__ = "query_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id = db.Column(db.Integer, nullable=True, index=True)
    dataset_name = db.Column(db.String(100), nullable=False)
    dataset_fingerprint = db.Column(db.String(64), nullable=False)
    query_mode = db.Column(db.String(16), nullable=False)
    query_cell_id = db.Column(db.Integer, nullable=True)
    top_k = db.Column(db.Integer, nullable=False)
    index_type = db.Column(db.String(16), nullable=False)
    metric = db.Column(db.String(16), nullable=False)
    filters = db.Column(db.JSON, nullable=False, default=dict)
    query_ms = db.Column(db.Float, nullable=False)
    returned = db.Column(db.Integer, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset_name,
            "query_mode": self.query_mode,
            "query_cell_id": self.query_cell_id,
            "top_k": self.top_k,
            "index_type": self.index_type,
            "metric": self.metric,
            "filters": dict(self.filters or {}),
            "query_ms": self.query_ms,
            "returned": self.returned,
            "created_at": self.created_at.isoformat(),
        }


class EvaluationLog(db.Model):
    __tablename__ = "evaluation_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id = db.Column(db.Integer, nullable=True, index=True)
    dataset_name = db.Column(db.String(100), nullable=False)
    dataset_fingerprint = db.Column(db.String(64), nullable=False)
    top_k = db.Column(db.Integer, nullable=False)
    n_queries = db.Column(db.Integer, nullable=False)
    metric = db.Column(db.String(16), nullable=False)
    index_types = db.Column(db.JSON, nullable=False)
    results = db.Column(db.JSON, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset_name,
            "top_k": self.top_k,
            "n_queries": self.n_queries,
            "metric": self.metric,
            "index_types": list(self.index_types or []),
            "results": list(self.results or []),
            "created_at": self.created_at.isoformat(),
        }
