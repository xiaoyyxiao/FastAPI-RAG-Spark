from __future__ import annotations

import json
from typing import Any

from core.database import db_session


class TraceService:
    def create_trace(
        self,
        trace_id: str,
        question: str,
        rewritten_question: str,
        answer_mode: str,
        conversation_id: int | None,
        provider_name: str,
        references: list[dict[str, Any]],
        stage_latencies_ms: dict[str, int],
        metadata: dict[str, Any],
    ) -> None:
        with db_session() as conn:
            conn.execute(
                """
                INSERT INTO qa_traces (
                    trace_id,
                    conversation_id,
                    question,
                    rewritten_question,
                    answer_mode,
                    provider_name,
                    retrieval_count,
                    rewrite_latency_ms,
                    retrieval_latency_ms,
                    generation_latency_ms,
                    total_latency_ms,
                    references_json,
                    metadata_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    trace_id,
                    conversation_id,
                    question,
                    rewritten_question,
                    answer_mode,
                    provider_name,
                    len(references),
                    stage_latencies_ms.get("rewrite", 0),
                    stage_latencies_ms.get("retrieval", 0),
                    stage_latencies_ms.get("generation", 0),
                    stage_latencies_ms.get("total", 0),
                    json.dumps(references, ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )

    def list_traces(self, limit: int = 20) -> list[dict[str, Any]]:
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT
                    trace_id,
                    conversation_id,
                    question,
                    rewritten_question,
                    answer_mode,
                    provider_name,
                    retrieval_count,
                    rewrite_latency_ms,
                    retrieval_latency_ms,
                    generation_latency_ms,
                    total_latency_ms,
                    created_at
                FROM qa_traces
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        with db_session() as conn:
            row = conn.execute(
                """
                SELECT
                    trace_id,
                    conversation_id,
                    question,
                    rewritten_question,
                    answer_mode,
                    provider_name,
                    retrieval_count,
                    rewrite_latency_ms,
                    retrieval_latency_ms,
                    generation_latency_ms,
                    total_latency_ms,
                    references_json,
                    metadata_json,
                    created_at
                FROM qa_traces
                WHERE trace_id = ?
                """,
                (trace_id,),
            ).fetchone()

        if not row:
            return None

        item = dict(row)
        item["references"] = json.loads(item.pop("references_json") or "[]")
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        return item


trace_service = TraceService()
