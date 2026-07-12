"""Persistent, validated, and atomically activated dataset lifecycle."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from werkzeug.datastructures import FileStorage

from app.core.extensions import db
from app.models import DatasetRecord
from app.services.data_loader import (
    file_sha256,
    load_dataset_file,
    semantic_dataset_fingerprint,
)
from app.services.search import search_service

ALLOWED_DATASET_SUFFIXES = frozenset({".h5ad", ".npy", ".csv"})


class DatasetConflictError(ValueError):
    """A resource with the requested stable identity already exists."""


class DatasetNotFoundError(ValueError):
    """The requested managed dataset does not exist."""


class ActiveDatasetError(ValueError):
    """An active dataset must be switched away before deletion."""


class DatasetService:
    def list_resources(self) -> list[dict]:
        with search_service.lifecycle_lock():
            search_service.ensure_initialized()
            active_id = search_service.dataset.record_id if search_service.dataset else None
            demo_active = search_service.dataset is not None and active_id is None
            resources = [
                {
                    "id": None,
                    "name": "demo",
                    "original_filename": None,
                    "file_format": "demo",
                    "source_type": "generated",
                    "use_obsm": None,
                    "n_cells": (
                        search_service.dataset.n_cells
                        if demo_active
                        else current_app.config["DEMO_N_CELLS"]
                    ),
                    "dim": (
                        search_service.dataset.dim
                        if demo_active
                        else current_app.config["DEMO_DIM"]
                    ),
                    "metadata_fields": ["cell_type"],
                    "fingerprint": search_service.dataset.fingerprint if demo_active else None,
                    "owner_id": None,
                    "active": demo_active,
                    "deletable": False,
                    "created_at": None,
                }
            ]
            records = DatasetRecord.query.order_by(DatasetRecord.created_at, DatasetRecord.id).all()
            resources.extend(record.to_dict(active=record.id == active_id) for record in records)
            return resources

    def load_many(self, dataset_ids: list[int]):
        """Load an ordered, verified snapshot of managed datasets under the lifecycle lock."""
        with search_service.lifecycle_lock():
            records = DatasetRecord.query.filter(DatasetRecord.id.in_(dataset_ids)).all()
            by_id = {record.id: record for record in records}
            missing = [dataset_id for dataset_id in dataset_ids if dataset_id not in by_id]
            if missing:
                raise DatasetNotFoundError(f"数据集不存在: {missing}")
            return [self._load_record(by_id[dataset_id]) for dataset_id in dataset_ids]

    def upload(
        self,
        uploaded: FileStorage,
        name: str | None,
        owner_id: int,
        use_obsm: str | None = "X_pca",
        activate: bool = True,
    ) -> dict:
        filename = Path(uploaded.filename or "").name
        if not filename:
            raise ValueError("必须选择数据文件")
        suffix = Path(filename).suffix.lower()
        self._validate_suffix(suffix)
        dataset_name = self._normalize_name(name or Path(filename).stem)
        self._ensure_unique_name(dataset_name)

        upload_dir = self._upload_dir()
        temp_path = upload_dir / f".{uuid.uuid4().hex}.uploading{suffix}"
        try:
            uploaded.save(temp_path)
            if not temp_path.is_file() or temp_path.stat().st_size == 0:
                raise ValueError("上传文件为空")
            return self._publish_temp(
                temp_path=temp_path,
                name=dataset_name,
                original_filename=filename,
                owner_id=owner_id,
                use_obsm=use_obsm,
                source_type="upload",
                activate=activate,
            )
        finally:
            temp_path.unlink(missing_ok=True)

    def import_existing(
        self,
        raw_path: str,
        name: str | None,
        owner_id: int,
        use_obsm: str | None = "X_pca",
        activate: bool = True,
    ) -> dict:
        source = self.resolve_managed_path(raw_path)
        dataset_name = self._normalize_name(name or source.stem)
        self._ensure_unique_name(dataset_name)
        upload_dir = self._upload_dir()
        temp_path = upload_dir / f".{uuid.uuid4().hex}.importing{source.suffix.lower()}"
        try:
            shutil.copyfile(source, temp_path)
            return self._publish_temp(
                temp_path=temp_path,
                name=dataset_name,
                original_filename=source.name,
                owner_id=owner_id,
                use_obsm=use_obsm,
                source_type="import",
                activate=activate,
            )
        finally:
            temp_path.unlink(missing_ok=True)

    def activate(self, dataset_id: int) -> dict:
        with search_service.lifecycle_lock():
            record = db.session.get(DatasetRecord, dataset_id)
            if record is None:
                raise DatasetNotFoundError("数据集不存在")
            dataset = self._load_record(record)
            snapshot = search_service.snapshot()
            try:
                status = search_service.set_dataset(dataset, index_type="flat", metric="l2")
                self._mark_active(record)
                db.session.commit()
            except Exception:
                db.session.rollback()
                search_service.restore(snapshot)
                raise
            return {"dataset": record.to_dict(active=True), "status": status}

    def activate_demo(self) -> dict:
        with search_service.lifecycle_lock():
            snapshot = search_service.snapshot()
            try:
                status = search_service.load_demo()
                for record in DatasetRecord.query.filter_by(is_active=True).all():
                    record.is_active = False
                db.session.commit()
            except Exception:
                db.session.rollback()
                search_service.restore(snapshot)
                raise
            return {"dataset": self.list_resources()[0], "status": status}

    def delete(self, dataset_id: int) -> dict:
        with search_service.lifecycle_lock():
            record = db.session.get(DatasetRecord, dataset_id)
            if record is None:
                raise DatasetNotFoundError("数据集不存在")
            active_id = search_service.dataset.record_id if search_service.dataset else None
            if record.is_active or record.id == active_id:
                raise ActiveDatasetError("不能删除当前活动数据集，请先切换到其他数据集")

            source = self._record_path(record)
            if not source.is_file():
                raise ValueError("数据集文件不存在，拒绝执行不完整删除")
            tombstone = source.with_name(f".{source.name}.{uuid.uuid4().hex}.deleting")
            from app.services.indexes import index_artifact_service

            cleanup = index_artifact_service.prepare_dataset_cleanup(record.id)
            try:
                source.replace(tombstone)
                name = record.name
                db.session.delete(record)
                db.session.commit()
            except Exception:
                db.session.rollback()
                cleanup.restore()
                if tombstone.exists() and not source.exists():
                    tombstone.replace(source)
                raise
            cleanup.finalize()
            tombstone.unlink(missing_ok=True)
            from app.services.federated import federated_search_service

            federated_search_service.invalidate_dataset(dataset_id)
            return {"message": "数据集已删除", "id": dataset_id, "name": name}

    def restore_active(self) -> dict | None:
        with search_service.lifecycle_lock():
            record = (
                DatasetRecord.query.filter_by(is_active=True).order_by(DatasetRecord.id).first()
            )
            if record is None:
                return None
            try:
                dataset = self._load_record(record)
                return search_service.set_dataset(dataset, index_type="flat", metric="l2")
            except Exception:
                record.is_active = False
                db.session.commit()
                raise

    def resolve_managed_path(self, raw_path: str) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("path 必须是非空字符串")
        requested = Path(raw_path.strip())
        if requested.is_absolute() or ".." in requested.parts:
            raise ValueError("path 只能指向 data 目录内的相对路径")
        if requested.parts and requested.parts[0] == "data":
            requested = Path(*requested.parts[1:])
        self._validate_suffix(requested.suffix.lower())
        path = self._inside_data_root(requested)
        if not path.is_file():
            raise ValueError(f"数据文件不存在: {requested.as_posix()}")
        return path

    def _publish_temp(
        self,
        temp_path: Path,
        name: str,
        original_filename: str,
        owner_id: int,
        use_obsm: str | None,
        source_type: str,
        activate: bool,
    ) -> dict:
        dataset = load_dataset_file(str(temp_path), use_obsm=use_obsm)
        source_fingerprint = file_sha256(str(temp_path))
        suffix = temp_path.suffix.lower()
        representation = use_obsm if suffix == ".h5ad" else None
        fingerprint = semantic_dataset_fingerprint(
            dataset,
            source_fingerprint,
            representation,
        )
        final_relative = Path("uploads") / f"{uuid.uuid4().hex}{suffix}"
        final_path = self._inside_data_root(final_relative)
        with search_service.lifecycle_lock():
            self._ensure_unique_name(name)
            temp_path.replace(final_path)

            snapshot = search_service.snapshot()
            swapped = False
            try:
                record = DatasetRecord(
                    name=name,
                    original_filename=original_filename,
                    stored_path=final_relative.as_posix(),
                    file_format=suffix[1:],
                    source_type=source_type,
                    use_obsm=representation,
                    n_cells=dataset.n_cells,
                    dim=dataset.dim,
                    metadata_fields=sorted(dataset.obs.keys()),
                    fingerprint=fingerprint,
                    owner_id=owner_id,
                    is_active=False,
                )
                db.session.add(record)
                db.session.flush()
                self._attach_record(dataset, record)
                status = None
                if activate:
                    status = search_service.set_dataset(dataset, index_type="flat", metric="l2")
                    swapped = True
                    self._mark_active(record)
                db.session.commit()
            except IntegrityError as exc:
                db.session.rollback()
                if swapped:
                    search_service.restore(snapshot)
                final_path.unlink(missing_ok=True)
                raise DatasetConflictError("数据集名称已存在") from exc
            except Exception:
                db.session.rollback()
                if swapped:
                    search_service.restore(snapshot)
                final_path.unlink(missing_ok=True)
                raise
            return {"dataset": record.to_dict(active=activate), "status": status}

    def _load_record(self, record: DatasetRecord):
        path = self._record_path(record)
        if not path.is_file():
            raise ValueError("数据集文件不存在")
        source_fingerprint = file_sha256(str(path))
        dataset = load_dataset_file(str(path), use_obsm=record.use_obsm)
        semantic_fingerprint = semantic_dataset_fingerprint(
            dataset,
            source_fingerprint,
            record.use_obsm if record.file_format == "h5ad" else None,
        )
        # Pre-v2 development records used the source-file hash directly.
        if record.fingerprint not in {source_fingerprint, semantic_fingerprint}:
            raise ValueError("数据集文件指纹不匹配，可能已被修改")
        self._attach_record(dataset, record)
        return dataset

    @staticmethod
    def _attach_record(dataset, record: DatasetRecord) -> None:
        dataset.name = record.name
        dataset.record_id = record.id
        dataset.fingerprint = record.fingerprint
        dataset.source_path = record.stored_path
        dataset.source_format = record.file_format

    @staticmethod
    def _mark_active(active: DatasetRecord) -> None:
        for record in DatasetRecord.query.filter_by(is_active=True).all():
            record.is_active = False
        active.is_active = True

    def _record_path(self, record: DatasetRecord) -> Path:
        return self._inside_data_root(Path(record.stored_path))

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
        if name.lower() == "demo":
            raise DatasetConflictError("demo 是保留数据集名称")
        return name

    @staticmethod
    def _validate_suffix(suffix: str) -> None:
        if suffix not in ALLOWED_DATASET_SUFFIXES:
            raise ValueError("仅支持 .h5ad、.npy 或 .csv 数据文件")

    @staticmethod
    def _ensure_unique_name(name: str) -> None:
        existing = DatasetRecord.query.filter(
            func.lower(DatasetRecord.name) == name.lower()
        ).first()
        if existing is not None:
            raise DatasetConflictError("数据集名称已存在")

    def _upload_dir(self) -> Path:
        directory = self._inside_data_root(Path("uploads"))
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _inside_data_root(self, relative: Path) -> Path:
        root = Path(current_app.config["DATA_DIR"]).resolve()
        root.mkdir(parents=True, exist_ok=True)
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("数据文件必须位于 data 目录内") from exc
        return path


dataset_service = DatasetService()
