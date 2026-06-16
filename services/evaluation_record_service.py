from __future__ import annotations

import json
from typing import Any

from core.database import db_session


class EvaluationRecordService:
    def create_evaluation(
        self,
        trace_id: str | None,
        question: str,
        answer: str,
        expected_answer: str | None,
        evaluation: dict[str, Any],
    ) -> None:
        with db_session() as conn:
            conn.execute(
                """
                INSERT INTO qa_evaluations (
                    trace_id,
                    question,
                    answer,
                    expected_answer,
                    verdict,
                    score,
                    groundedness,
                    relevance,
                    completeness,
                    clarity,
                    strengths_json,
                    issues_json,
                    suggestions_json,
                    reason,
                    raw_evaluation,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    trace_id,
                    question,
                    answer,
                    expected_answer,
                    evaluation.get("verdict"),
                    evaluation.get("score"),
                    evaluation.get("groundedness"),
                    evaluation.get("relevance"),
                    evaluation.get("completeness"),
                    evaluation.get("clarity"),
                    json.dumps(evaluation.get("strengths", []), ensure_ascii=False),
                    json.dumps(evaluation.get("issues", []), ensure_ascii=False),
                    json.dumps(evaluation.get("suggestions", []), ensure_ascii=False),
                    evaluation.get("reason"),
                    evaluation.get("raw_evaluation"),
                ),
            )

    def list_evaluations(self, limit: int = 20) -> list[dict[str, Any]]:
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    trace_id,
                    question,
                    verdict,
                    score,
                    groundedness,
                    relevance,
                    completeness,
                    clarity,
                    created_at
                FROM qa_evaluations
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [dict(row) for row in rows]


evaluation_record_service = EvaluationRecordService()
