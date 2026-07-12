"""Dataset-bound ANN index persistence with verified manifests."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.core.extensions import db
from app.models import IndexArtifact
from app.services.data_loader import file_sha256
from app.services.index import create_index
from app.services.search import search_service


MANIFEST_SCHEMA_VERSION = 1


class IndexConflictError(ValueError):
    """An index name already exists for the same dataset fingerprint."""


class IndexNotFoundError(ValueError):
    """The requested persisted index record does not exist."""


class ActiveIndexError(ValueError):
    """The active index cannot be deleted before another index is selected."""


class IncompatibleIndexError(ValueError):
    """The artifact does not match the active dataset or its manifest."""


class IndexArtifactService:
    def list_artifacts(self, dataset_id: int | None = None) -> list[dict]:
        search_service.ensure_initialized()
        query = IndexArtifact.query
        if dataset_id is not None:
            query = query.filter_by(dataset_id=dataset_id)
        records = query.order_by(IndexArtifact.created_at, IndexArtifact.id).all()
        active_fingerprint = search_service.dataset.fingerprint
        return [
            record.to_dict(
                active=record.id == search_service.index_record_id,
                compatible=record.dataset_fingerprint == active_fingerprint,
            )
            for record in records
        ]

    def save_current(self, name: str | None, owner_id: int) -> dict:
        with search_service.locked_state() as state:
            dataset, index, index_type, metric = state
            if not dataset.fingerprint:
                raise ValueError("当前数据集缺少稳定指纹，无法保存索引")
            artifact_name = self._normalize_name(
                name or f"{dataset.name}-{index_type}-{metric}-{uuid.uuid4().hex[:8]}"
            )
            self._ensure_unique_name(dataset.fingerprint, artifact_name)

            extension = ".npy" if index_type == "flat" else ".faiss"
            token = uuid.uuid4().hex
            artifact_relative = Path(f"{token}{extension}")
            manifest_relative = Path(f"{token}.json")
            artifact_path = self._inside_index_root(artifact_relative)
            manifest_path = self._inside_index_root(manifest_relative)
            temp_artifact = self._inside_index_root(Path(f".{token}.tmp{extension}"))
            temp_manifest = self._inside_index_root(Path(f".{token}.tmp.json"))

            published: list[Path] = []
            try:
                index.save(str(temp_artifact))
                fingerprint = file_sha256(str(temp_artifact))
                library_version = self._library_version(index_type)
                manifest = {
                    "schema_version": MANIFEST_SCHEMA_VERSION,
                    "name": artifact_name,
                    "dataset_id": dataset.record_id,
                    "dataset_name": dataset.name,
                    "dataset_fingerprint": dataset.fingerprint,
                    "index_type": index_type,
                    "metric": metric,
                    "dim": dataset.dim,
                    "n_items": dataset.n_cells,
                    "parameters": index.parameters(),
                    "artifact": artifact_relative.name,
                    "artifact_fingerprint": fingerprint,
                    "library_version": library_version,
                }
                self._write_json(temp_manifest, manifest)
                os.replace(temp_artifact, artifact_path)
                published.append(artifact_path)
                os.replace(temp_manifest, manifest_path)
                published.append(manifest_path)

                record = IndexArtifact(
                    name=artifact_name,
                    dataset_id=dataset.record_id,
                    dataset_name=dataset.name,
                    dataset_fingerprint=dataset.fingerprint,
                    index_type=index_type,
                    metric=metric,
                    dim=dataset.dim,
                    n_items=dataset.n_cells,
                    parameters=index.parameters(),
                    stored_path=artifact_relative.as_posix(),
                    manifest_path=manifest_relative.as_posix(),
                    artifact_fingerprint=fingerprint,
                    library_version=library_version,
                    owner_id=owner_id,
                )
                db.session.add(record)
                db.session.commit()
                status = search_service.mark_index_persisted(record.id)
            except IntegrityError as exc:
                db.session.rollback()
                for path in published:
                    path.unlink(missing_ok=True)
                raise IndexConflictError("当前数据集已存在同名索引") from exc
            except Exception:
                db.session.rollback()
                for path in published:
                    path.unlink(missing_ok=True)
                raise
            finally:
                temp_artifact.unlink(missing_ok=True)
                temp_manifest.unlink(missing_ok=True)
        return {
            "artifact": record.to_dict(active=True, compatible=True),
            "status": status,
        }

    def load(self, artifact_id: int) -> dict:
        record = db.session.get(IndexArtifact, artifact_id)
        if record is None:
            raise IndexNotFoundError("索引不存在")
        search_service.ensure_initialized()
        dataset = search_service.dataset
        if record.dataset_fingerprint != dataset.fingerprint:
            raise IncompatibleIndexError("索引与当前数据集不匹配")

        artifact_path = self._record_artifact_path(record)
        manifest_path = self._record_manifest_path(record)
        manifest = self._validate_files(record, artifact_path, manifest_path)
        candidate = create_index(record.index_type, record.dim, record.metric)
        candidate.load(str(artifact_path))
        if candidate.n_items != record.n_items:
            raise IncompatibleIndexError("索引条目数与清单不一致")
        status = search_service.install_index(
            candidate,
            record.index_type,
            record.metric,
            record.id,
            record.dataset_fingerprint,
        )
        return {
            "artifact": record.to_dict(active=True, compatible=True),
            "manifest": manifest,
            "status": status,
        }

    def delete(self, artifact_id: int) -> dict:
        record = db.session.get(IndexArtifact, artifact_id)
        if record is None:
            raise IndexNotFoundError("索引不存在")
        if record.id == search_service.index_record_id:
            raise ActiveIndexError("不能删除当前加载的索引，请先构建或加载其他索引")
        cleanup = self._stage_cleanup([record])
        try:
            name = record.name
            db.session.commit()
        except Exception:
            db.session.rollback()
            cleanup.restore()
            raise
        cleanup.finalize()
        return {"message": "索引已删除", "id": artifact_id, "name": name}

    def prepare_dataset_cleanup(self, dataset_id: int) -> "ArtifactCleanup":
        records = IndexArtifact.query.filter_by(dataset_id=dataset_id).all()
        if any(record.id == search_service.index_record_id for record in records):
            raise ActiveIndexError("数据集仍有关联的活动索引")
        return self._stage_cleanup(records)

    def _stage_cleanup(self, records: list[IndexArtifact]) -> "ArtifactCleanup":
        moved: list[tuple[Path, Path]] = []
        try:
            for record in records:
                for source in (
                    self._record_artifact_path(record),
                    self._record_manifest_path(record),
                ):
                    if source.exists():
                        tombstone = source.with_name(
                            f".{source.name}.{uuid.uuid4().hex}.deleting"
                        )
                        source.replace(tombstone)
                        moved.append((source, tombstone))
                db.session.delete(record)
        except Exception:
            ArtifactCleanup(moved).restore()
            raise
        return ArtifactCleanup(moved)

    def _validate_files(
        self,
        record: IndexArtifact,
        artifact_path: Path,
        manifest_path: Path,
    ) -> dict:
        if not artifact_path.is_file() or not manifest_path.is_file():
            raise IncompatibleIndexError("索引文件或清单不存在")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise IncompatibleIndexError("索引清单损坏") from exc
        expected = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "name": record.name,
            "dataset_id": record.dataset_id,
            "dataset_name": record.dataset_name,
            "dataset_fingerprint": record.dataset_fingerprint,
            "index_type": record.index_type,
            "metric": record.metric,
            "dim": record.dim,
            "n_items": record.n_items,
            "parameters": dict(record.parameters or {}),
            "artifact": artifact_path.name,
            "artifact_fingerprint": record.artifact_fingerprint,
            "library_version": record.library_version,
        }
        if not isinstance(manifest, dict) or any(
            manifest.get(key) != value for key, value in expected.items()
        ):
            raise IncompatibleIndexError("索引清单与数据库记录不一致")
        if file_sha256(str(artifact_path)) != record.artifact_fingerprint:
            raise IncompatibleIndexError("索引文件指纹不匹配，可能已被修改")
        return manifest

    @staticmethod
    def _normalize_name(value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("name 必须是字符串")
        name = value.strip()
        if not name or len(name) > 100:
            raise ValueError("name 长度必须为 1 到 100 个字符")
        if any(character in name for character in ("/", "\\")) or any(
            ord(character) < 32 for character in name
        ):
            raise ValueError("name 包含非法字符")
        return name

    @staticmethod
    def _ensure_unique_name(dataset_fingerprint: str, name: str) -> None:
        existing = IndexArtifact.query.filter(
            IndexArtifact.dataset_fingerprint == dataset_fingerprint,
            func.lower(IndexArtifact.name) == name.lower(),
        ).first()
        if existing is not None:
            raise IndexConflictError("当前数据集已存在同名索引")

    @staticmethod
    def _library_version(index_type: str) -> str:
        if index_type == "flat":
            return f"numpy-{np.__version__}"
        import faiss

        return f"faiss-{faiss.__version__}"

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        with open(path, "x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())

    def _record_artifact_path(self, record: IndexArtifact) -> Path:
        return self._inside_index_root(Path(record.stored_path))

    def _record_manifest_path(self, record: IndexArtifact) -> Path:
        return self._inside_index_root(Path(record.manifest_path))

    @staticmethod
    def _inside_index_root(relative: Path) -> Path:
        root = Path(current_app.config["INDEX_DIR"]).resolve()
        root.mkdir(parents=True, exist_ok=True)
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("索引文件必须位于配置的索引目录内") from exc
        return path


@dataclass
class ArtifactCleanup:
    moved: list[tuple[Path, Path]]

    def restore(self) -> None:
        for source, tombstone in reversed(self.moved):
            if tombstone.exists() and not source.exists():
                tombstone.replace(source)

    def finalize(self) -> None:
        for _, tombstone in self.moved:
            tombstone.unlink(missing_ok=True)


index_artifact_service = IndexArtifactService()
