from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from utils.password_utils import encrypt_password


DB_PATH = Path("docs.db")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_session() -> Iterator[sqlite3.Connection]:
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db_session() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                content TEXT,
                file_size INTEGER NOT NULL DEFAULT 0,
                file_type TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS document_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                started_at TEXT,
                finished_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (document_id) REFERENCES documents(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS document_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (document_id) REFERENCES documents(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'employee',
                is_first_login INTEGER NOT NULL DEFAULT 1
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                mode TEXT,
                doc_id INTEGER,
                references_json TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS qa_traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL UNIQUE,
                conversation_id INTEGER,
                question TEXT NOT NULL,
                rewritten_question TEXT,
                answer_mode TEXT,
                provider_name TEXT,
                retrieval_count INTEGER NOT NULL DEFAULT 0,
                rewrite_latency_ms INTEGER NOT NULL DEFAULT 0,
                retrieval_latency_ms INTEGER NOT NULL DEFAULT 0,
                generation_latency_ms INTEGER NOT NULL DEFAULT 0,
                total_latency_ms INTEGER NOT NULL DEFAULT 0,
                references_json TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS qa_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                rating TEXT NOT NULL,
                comment TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS qa_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                expected_answer TEXT,
                verdict TEXT,
                score INTEGER,
                groundedness INTEGER,
                relevance INTEGER,
                completeness INTEGER,
                clarity INTEGER,
                strengths_json TEXT,
                issues_json TEXT,
                suggestions_json TEXT,
                reason TEXT,
                raw_evaluation TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

        _ensure_documents_schema(cursor)
        _ensure_user_info_schema(cursor)
        _ensure_conversations_schema(cursor)
        _ensure_messages_schema(cursor)
        _ensure_qa_traces_schema(cursor)
        _ensure_qa_feedback_schema(cursor)
        _ensure_qa_evaluations_schema(cursor)
        _ensure_default_admin(cursor)


def _ensure_documents_schema(cursor: sqlite3.Cursor) -> None:
    columns = {row["name"] for row in cursor.execute("PRAGMA table_info(documents)").fetchall()}

    if "filename" not in columns and "name" in columns:
        cursor.execute("ALTER TABLE documents RENAME COLUMN name TO filename")
        columns.remove("name")
        columns.add("filename")

    if "content" not in columns:
        cursor.execute("ALTER TABLE documents ADD COLUMN content TEXT")
    if "file_size" not in columns:
        cursor.execute("ALTER TABLE documents ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0")
    if "file_type" not in columns:
        cursor.execute("ALTER TABLE documents ADD COLUMN file_type TEXT NOT NULL DEFAULT ''")
    if "status" not in columns:
        cursor.execute("ALTER TABLE documents ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")
    if "error_message" not in columns:
        cursor.execute("ALTER TABLE documents ADD COLUMN error_message TEXT")
    if "created_at" not in columns:
        cursor.execute("ALTER TABLE documents ADD COLUMN created_at TEXT")
        cursor.execute("UPDATE documents SET created_at = datetime('now') WHERE created_at IS NULL")
    if "updated_at" not in columns:
        cursor.execute("ALTER TABLE documents ADD COLUMN updated_at TEXT")
        cursor.execute("UPDATE documents SET updated_at = datetime('now') WHERE updated_at IS NULL")


def _ensure_user_info_schema(cursor: sqlite3.Cursor) -> None:
    columns = {row["name"] for row in cursor.execute("PRAGMA table_info(user_info)").fetchall()}

    if "is_first_login" not in columns:
        cursor.execute("ALTER TABLE user_info ADD COLUMN is_first_login INTEGER NOT NULL DEFAULT 1")


def _ensure_default_admin(cursor: sqlite3.Cursor) -> None:
    cursor.execute("SELECT 1 FROM user_info WHERE username = ?", ("admin",))
    if cursor.fetchone():
        return

    cursor.execute(
        """
        INSERT INTO user_info (username, password, role, is_first_login)
        VALUES (?, ?, ?, ?)
        """,
        ("admin", encrypt_password("admin123456"), "admin", 0),
    )


def _ensure_conversations_schema(cursor: sqlite3.Cursor) -> None:
    columns = {row["name"] for row in cursor.execute("PRAGMA table_info(conversations)").fetchall()}

    if "title" not in columns:
        cursor.execute("ALTER TABLE conversations ADD COLUMN title TEXT NOT NULL DEFAULT ''")
    if "created_at" not in columns:
        cursor.execute("ALTER TABLE conversations ADD COLUMN created_at TEXT")
        cursor.execute("UPDATE conversations SET created_at = datetime('now') WHERE created_at IS NULL")
    if "updated_at" not in columns:
        cursor.execute("ALTER TABLE conversations ADD COLUMN updated_at TEXT")
        cursor.execute("UPDATE conversations SET updated_at = datetime('now') WHERE updated_at IS NULL")


def _ensure_messages_schema(cursor: sqlite3.Cursor) -> None:
    columns = {row["name"] for row in cursor.execute("PRAGMA table_info(messages)").fetchall()}

    if "mode" not in columns:
        cursor.execute("ALTER TABLE messages ADD COLUMN mode TEXT")
    if "doc_id" not in columns:
        cursor.execute("ALTER TABLE messages ADD COLUMN doc_id INTEGER")
    if "references_json" not in columns:
        cursor.execute("ALTER TABLE messages ADD COLUMN references_json TEXT")
    if "created_at" not in columns:
        cursor.execute("ALTER TABLE messages ADD COLUMN created_at TEXT")
        cursor.execute("UPDATE messages SET created_at = datetime('now') WHERE created_at IS NULL")


def _ensure_qa_traces_schema(cursor: sqlite3.Cursor) -> None:
    columns = {row["name"] for row in cursor.execute("PRAGMA table_info(qa_traces)").fetchall()}

    if "rewritten_question" not in columns:
        cursor.execute("ALTER TABLE qa_traces ADD COLUMN rewritten_question TEXT")
    if "answer_mode" not in columns:
        cursor.execute("ALTER TABLE qa_traces ADD COLUMN answer_mode TEXT")
    if "provider_name" not in columns:
        cursor.execute("ALTER TABLE qa_traces ADD COLUMN provider_name TEXT")
    if "retrieval_count" not in columns:
        cursor.execute("ALTER TABLE qa_traces ADD COLUMN retrieval_count INTEGER NOT NULL DEFAULT 0")
    if "rewrite_latency_ms" not in columns:
        cursor.execute("ALTER TABLE qa_traces ADD COLUMN rewrite_latency_ms INTEGER NOT NULL DEFAULT 0")
    if "retrieval_latency_ms" not in columns:
        cursor.execute("ALTER TABLE qa_traces ADD COLUMN retrieval_latency_ms INTEGER NOT NULL DEFAULT 0")
    if "generation_latency_ms" not in columns:
        cursor.execute("ALTER TABLE qa_traces ADD COLUMN generation_latency_ms INTEGER NOT NULL DEFAULT 0")
    if "total_latency_ms" not in columns:
        cursor.execute("ALTER TABLE qa_traces ADD COLUMN total_latency_ms INTEGER NOT NULL DEFAULT 0")
    if "references_json" not in columns:
        cursor.execute("ALTER TABLE qa_traces ADD COLUMN references_json TEXT")
    if "metadata_json" not in columns:
        cursor.execute("ALTER TABLE qa_traces ADD COLUMN metadata_json TEXT")
    if "created_at" not in columns:
        cursor.execute("ALTER TABLE qa_traces ADD COLUMN created_at TEXT")
        cursor.execute("UPDATE qa_traces SET created_at = datetime('now') WHERE created_at IS NULL")


def _ensure_qa_feedback_schema(cursor: sqlite3.Cursor) -> None:
    columns = {row["name"] for row in cursor.execute("PRAGMA table_info(qa_feedback)").fetchall()}

    if "comment" not in columns:
        cursor.execute("ALTER TABLE qa_feedback ADD COLUMN comment TEXT")
    if "created_at" not in columns:
        cursor.execute("ALTER TABLE qa_feedback ADD COLUMN created_at TEXT")
        cursor.execute("UPDATE qa_feedback SET created_at = datetime('now') WHERE created_at IS NULL")


def _ensure_qa_evaluations_schema(cursor: sqlite3.Cursor) -> None:
    columns = {row["name"] for row in cursor.execute("PRAGMA table_info(qa_evaluations)").fetchall()}

    for column_name, column_type in [
        ("trace_id", "TEXT"),
        ("expected_answer", "TEXT"),
        ("verdict", "TEXT"),
        ("score", "INTEGER"),
        ("groundedness", "INTEGER"),
        ("relevance", "INTEGER"),
        ("completeness", "INTEGER"),
        ("clarity", "INTEGER"),
        ("strengths_json", "TEXT"),
        ("issues_json", "TEXT"),
        ("suggestions_json", "TEXT"),
        ("reason", "TEXT"),
        ("raw_evaluation", "TEXT"),
    ]:
        if column_name not in columns:
            cursor.execute(f"ALTER TABLE qa_evaluations ADD COLUMN {column_name} {column_type}")

    if "created_at" not in columns:
        cursor.execute("ALTER TABLE qa_evaluations ADD COLUMN created_at TEXT")
        cursor.execute("UPDATE qa_evaluations SET created_at = datetime('now') WHERE created_at IS NULL")
