"""Persistence and bounded retrieval for user-visible query/evaluation history."""

from __future__ import annotations

from app.core.extensions import db
from app.models import EvaluationLog, QueryLog


class HistoryService:
    def record_query(self, user_id: int, request_data: dict, result: dict) -> QueryLog:
        query_mode = "vector" if request_data.get("vector") is not None else "cell"
        record = QueryLog(
            user_id=user_id,
            dataset_id=result["dataset_id"],
            dataset_name=result["dataset"],
            dataset_fingerprint=result["dataset_fingerprint"],
            query_mode=query_mode,
            query_cell_id=request_data.get("cell_id") if query_mode == "cell" else None,
            top_k=int(request_data.get("top_k")),
            index_type=result["index_type"],
            metric=result["metric"],
            filters=(
                {"cell_type": request_data["cell_type"]} if request_data.get("cell_type") else {}
            ),
            query_ms=float(result["query_ms"]),
            returned=int(result["returned"]),
        )
        db.session.add(record)
        db.session.commit()
        return record

    def record_evaluation(
        self,
        user_id: int,
        dataset,
        top_k: int,
        n_queries: int,
        metric: str,
        index_types: list[str],
        results: list[dict],
    ) -> EvaluationLog:
        record = EvaluationLog(
            user_id=user_id,
            dataset_id=dataset.record_id,
            dataset_name=dataset.name,
            dataset_fingerprint=dataset.fingerprint,
            top_k=top_k,
            n_queries=n_queries,
            metric=metric,
            index_types=index_types,
            results=results,
        )
        db.session.add(record)
        db.session.commit()
        return record

    @staticmethod
    def list_queries(user_id: int, is_admin: bool, limit: int) -> list[dict]:
        query = QueryLog.query
        if not is_admin:
            query = query.filter_by(user_id=user_id)
        records = query.order_by(QueryLog.created_at.desc(), QueryLog.id.desc()).limit(limit)
        return [record.to_dict() for record in records]

    @staticmethod
    def list_evaluations(user_id: int, is_admin: bool, limit: int) -> list[dict]:
        query = EvaluationLog.query
        if not is_admin:
            query = query.filter_by(user_id=user_id)
        records = query.order_by(
            EvaluationLog.created_at.desc(),
            EvaluationLog.id.desc(),
        ).limit(limit)
        return [record.to_dict() for record in records]


history_service = HistoryService()
