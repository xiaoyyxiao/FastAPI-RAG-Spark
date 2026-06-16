from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from core.database import db_session


class ConversationService:
    def get_or_create_conversation(self, conversation_id: int | None, first_question: str) -> dict[str, Any]:
        if conversation_id is None:
            return self.create_conversation(first_question)

        with db_session() as conn:
            row = conn.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Conversation ID {conversation_id} not found")

        return dict(row)

    def create_conversation(self, title_seed: str) -> dict[str, Any]:
        title = title_seed.strip()[:40] or "New conversation"

        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversations (title, created_at, updated_at)
                VALUES (?, datetime('now'), datetime('now'))
                """,
                (title,),
            )
            conversation_id = int(cursor.lastrowid)
            row = conn.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()

        return dict(row)

    def list_conversations(self) -> list[dict[str, Any]]:
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.id,
                    c.title,
                    c.created_at,
                    c.updated_at,
                    (
                        SELECT COUNT(*)
                        FROM messages m
                        WHERE m.conversation_id = c.id
                    ) AS message_count
                FROM conversations c
                ORDER BY c.updated_at DESC, c.id DESC
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def get_conversation_messages(self, conversation_id: int) -> list[dict[str, Any]]:
        with db_session() as conn:
            conversation = conn.execute(
                "SELECT id FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if not conversation:
                raise HTTPException(status_code=404, detail=f"Conversation ID {conversation_id} not found")

            rows = conn.execute(
                """
                SELECT id, role, content, mode, doc_id, references_json, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id ASC
                """,
                (conversation_id,),
            ).fetchall()

        messages = []
        for row in rows:
            item = dict(row)
            item["references"] = json.loads(item["references_json"]) if item["references_json"] else []
            item.pop("references_json", None)
            messages.append(item)
        return messages

    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        mode: str | None = None,
        doc_id: int | None = None,
        references: list[dict[str, Any]] | None = None,
    ) -> int:
        references_json = json.dumps(references or [], ensure_ascii=False)

        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO messages (conversation_id, role, content, mode, doc_id, references_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (conversation_id, role, content, mode, doc_id, references_json),
            )
            message_id = int(cursor.lastrowid)
            conn.execute(
                """
                UPDATE conversations
                SET updated_at = datetime('now')
                WHERE id = ?
                """,
                (conversation_id,),
            )
            return message_id

    def get_recent_history(self, conversation_id: int, limit: int = 6) -> list[dict[str, Any]]:
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT role, content, mode, doc_id, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()

        return [dict(row) for row in reversed(rows)]


conversation_service = ConversationService()
