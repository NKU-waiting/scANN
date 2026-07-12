"""Metadata for dataset-bound persisted ANN index artifacts."""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.extensions import db


class IndexArtifact(db.Model):
    __tablename__ = "index_artifacts"
    __table_args__ = (
        db.UniqueConstraint("dataset_fingerprint", "name", name="uq_index_dataset_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    dataset_id = db.Column(
        db.Integer,
        db.ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    dataset_name = db.Column(db.String(100), nullable=False)
    dataset_fingerprint = db.Column(db.String(64), nullable=False, index=True)
    index_type = db.Column(db.String(16), nullable=False)
    metric = db.Column(db.String(16), nullable=False)
    dim = db.Column(db.Integer, nullable=False)
    n_items = db.Column(db.Integer, nullable=False)
    parameters = db.Column(db.JSON, nullable=False, default=dict)
    stored_path = db.Column(db.String(255), unique=True, nullable=False)
    manifest_path = db.Column(db.String(255), unique=True, nullable=False)
    artifact_fingerprint = db.Column(db.String(64), nullable=False)
    library_version = db.Column(db.String(64), nullable=False)
    owner_id = db.Column(db.Integer, nullable=True, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self, active: bool = False, compatible: bool = False) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset_name,
            "dataset_fingerprint": self.dataset_fingerprint,
            "index_type": self.index_type,
            "metric": self.metric,
            "dim": self.dim,
            "n_items": self.n_items,
            "parameters": dict(self.parameters or {}),
            "artifact_fingerprint": self.artifact_fingerprint,
            "library_version": self.library_version,
            "owner_id": self.owner_id,
            "active": active,
            "compatible": compatible,
            "deletable": not active,
            "created_at": self.created_at.isoformat(),
        }
