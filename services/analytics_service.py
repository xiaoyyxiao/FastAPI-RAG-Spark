from __future__ import annotations

import json
from typing import Any

from core.database import db_session


class AnalyticsService:
    def get_overview(self) -> dict[str, Any]:
        with db_session() as conn:
            traces_total = conn.execute("SELECT COUNT(*) AS count FROM qa_traces").fetchone()["count"]
            feedback_total = conn.execute("SELECT COUNT(*) AS count FROM qa_feedback").fetchone()["count"]
            evaluations_total = conn.execute("SELECT COUNT(*) AS count FROM qa_evaluations").fetchone()["count"]

            provider_rows = conn.execute(
                """
                SELECT provider_name, COUNT(*) AS count
                FROM qa_traces
                GROUP BY provider_name
                ORDER BY count DESC
                """
            ).fetchall()

            feedback_rows = conn.execute(
                """
                SELECT rating, COUNT(*) AS count
                FROM qa_feedback
                GROUP BY rating
                """
            ).fetchall()

            evaluation_stats = conn.execute(
                """
                SELECT
                    AVG(score) AS avg_score,
                    SUM(CASE WHEN verdict = 'pass' THEN 1 ELSE 0 END) AS pass_count,
                    SUM(CASE WHEN verdict = 'fail' THEN 1 ELSE 0 END) AS fail_count
                FROM qa_evaluations
                """
            ).fetchone()

            recent_traces = conn.execute(
                """
                SELECT total_latency_ms, provider_name, metadata_json
                FROM qa_traces
                ORDER BY id DESC
                LIMIT 50
                """
            ).fetchall()

        provider_usage = {row["provider_name"] or "unknown": row["count"] for row in provider_rows}
        feedback_distribution = {row["rating"]: row["count"] for row in feedback_rows}

        fallback_count = 0
        latency_values = []
        overlap_values = []
        for row in recent_traces:
            latency_values.append(row["total_latency_ms"])
            metadata = json.loads(row["metadata_json"] or "{}")
            if metadata.get("used_fallback"):
                fallback_count += 1
            retrieval_quality = metadata.get("retrieval_quality") or {}
            avg_overlap = retrieval_quality.get("avg_query_overlap")
            if isinstance(avg_overlap, (int, float)):
                overlap_values.append(avg_overlap)

        return {
            "totals": {
                "traces": traces_total,
                "feedback": feedback_total,
                "evaluations": evaluations_total,
            },
            "provider_usage": provider_usage,
            "feedback_distribution": feedback_distribution,
            "evaluation_summary": {
                "avg_score": round(evaluation_stats["avg_score"] or 0, 2),
                "pass_count": evaluation_stats["pass_count"] or 0,
                "fail_count": evaluation_stats["fail_count"] or 0,
            },
            "recent_runtime_summary": {
                "fallback_count_last_50": fallback_count,
                "avg_total_latency_ms_last_50": round(sum(latency_values) / len(latency_values), 2) if latency_values else 0,
                "avg_query_overlap_last_50": round(sum(overlap_values) / len(overlap_values), 4) if overlap_values else 0,
            },
        }

    def list_low_score_evaluations(self, limit: int = 10, score_threshold: int = 60) -> list[dict[str, Any]]:
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
                    reason,
                    created_at
                FROM qa_evaluations
                WHERE score IS NOT NULL AND score <= ?
                ORDER BY score ASC, id DESC
                LIMIT ?
                """,
                (score_threshold, limit),
            ).fetchall()

        return [dict(row) for row in rows]

    def list_recent_fallbacks(self, limit: int = 10) -> list[dict[str, Any]]:
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT
                    trace_id,
                    question,
                    rewritten_question,
                    provider_name,
                    total_latency_ms,
                    metadata_json,
                    created_at
                FROM qa_traces
                ORDER BY id DESC
                LIMIT 100
                """
            ).fetchall()

        items = []
        for row in rows:
            metadata = json.loads(row["metadata_json"] or "{}")
            if not metadata.get("used_fallback"):
                continue
            item = dict(row)
            item["metadata"] = metadata
            item.pop("metadata_json", None)
            items.append(item)
            if len(items) >= limit:
                break

        return items

    def list_low_overlap_traces(self, limit: int = 10, overlap_threshold: float = 0.2) -> list[dict[str, Any]]:
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT
                    trace_id,
                    question,
                    rewritten_question,
                    answer_mode,
                    provider_name,
                    retrieval_count,
                    total_latency_ms,
                    metadata_json,
                    created_at
                FROM qa_traces
                ORDER BY id DESC
                LIMIT 200
                """
            ).fetchall()

        items = []
        for row in rows:
            metadata = json.loads(row["metadata_json"] or "{}")
            retrieval_quality = metadata.get("retrieval_quality") or {}
            avg_overlap = retrieval_quality.get("avg_query_overlap")
            if avg_overlap is None or avg_overlap > overlap_threshold:
                continue

            item = dict(row)
            item["metadata"] = metadata
            item["retrieval_quality"] = retrieval_quality
            item.pop("metadata_json", None)
            items.append(item)
            if len(items) >= limit:
                break

        return items


analytics_service = AnalyticsService()
