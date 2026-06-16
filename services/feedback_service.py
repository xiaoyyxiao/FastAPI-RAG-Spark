from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from core.database import db_session


class FeedbackService:
    def add_feedback(self, trace_id: str, rating: str, comment: str | None = None) -> None:
        with db_session() as conn:
            trace = conn.execute(
                "SELECT 1 FROM qa_traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
            if not trace:
                raise HTTPException(status_code=404, detail=f"Trace ID {trace_id} not found")

            conn.execute(
                """
                INSERT INTO qa_feedback (trace_id, rating, comment, created_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (trace_id, rating, comment),
            )

    def list_feedback(self, limit: int = 20) -> list[dict[str, Any]]:
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT id, trace_id, rating, comment, created_at
                FROM qa_feedback
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [dict(row) for row in rows]


feedback_service = FeedbackService()
