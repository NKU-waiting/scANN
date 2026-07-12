"""Persistent metadata for managed single-cell vector datasets."""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.extensions import db


class DatasetRecord(db.Model):
    __tablename__ = "datasets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(255), unique=True, nullable=False)
    file_format = db.Column(db.String(16), nullable=False)
    source_type = db.Column(db.String(16), nullable=False, default="upload")
    use_obsm = db.Column(db.String(100), nullable=True)
    n_cells = db.Column(db.Integer, nullable=False)
    dim = db.Column(db.Integer, nullable=False)
    metadata_fields = db.Column(db.JSON, nullable=False, default=list)
    fingerprint = db.Column(db.String(64), nullable=False, index=True)
    owner_id = db.Column(db.Integer, nullable=True, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self, active: bool | None = None) -> dict:
        is_active = self.is_active if active is None else active
        return {
            "id": self.id,
            "name": self.name,
            "original_filename": self.original_filename,
            "file_format": self.file_format,
            "source_type": self.source_type,
            "use_obsm": self.use_obsm,
            "n_cells": self.n_cells,
            "dim": self.dim,
            "metadata_fields": list(self.metadata_fields or []),
            "fingerprint": self.fingerprint,
            "owner_id": self.owner_id,
            "active": is_active,
            "deletable": not is_active,
            "created_at": self.created_at.isoformat(),
        }
