from __future__ import annotations

import io
import sqlite3
from dataclasses import dataclass
from typing import Any

from docx import Document
from fastapi import HTTPException, UploadFile
from PyPDF2 import PdfReader

from config.settings import settings
from core.database import db_session
from core.rag.bootstrap import bootstrap_rag_store
from core.rag.rag_service import add_document_to_rag, split_text


@dataclass
class StoredUpload:
    filename: str
    file_type: str
    file_size: int
    content_bytes: bytes


class DocumentIngestionService:
    def create_document(self, upload: StoredUpload) -> tuple[int, int]:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO documents (filename, content, file_size, file_type, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', datetime('now'), datetime('now'))
                """,
                (upload.filename, "", upload.file_size, upload.file_type),
            )
            document_id = int(cursor.lastrowid)
            cursor.execute(
                """
                INSERT INTO document_jobs (document_id, job_type, status, created_at, updated_at)
                VALUES (?, 'ingest', 'pending', datetime('now'), datetime('now'))
                """,
                (document_id,),
            )
            job_id = int(cursor.lastrowid)
            return document_id, job_id

    def ingest_document(self, document_id: int, job_id: int, upload: StoredUpload) -> None:
        self._mark_job_started(document_id, job_id)

        try:
            text = self._extract_text(upload)
            chunks = split_text(text)

            with db_session() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
                cursor.executemany(
                    """
                    INSERT INTO document_chunks (document_id, chunk_index, chunk_text)
                    VALUES (?, ?, ?)
                    """,
                    [(document_id, index, chunk) for index, chunk in enumerate(chunks)],
                )
                cursor.execute(
                    """
                    UPDATE documents
                    SET content = ?, status = 'processing', error_message = NULL, updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (text, document_id),
                )

            add_document_to_rag(document_id=document_id, text=text)
            self._mark_job_succeeded(document_id, job_id)
        except HTTPException as exc:
            self._mark_job_failed(document_id, job_id, exc.detail)
        except Exception as exc:
            self._mark_job_failed(document_id, job_id, str(exc))

    def list_documents(self) -> list[dict[str, Any]]:
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT id, filename, file_size, file_type, status, error_message, LENGTH(COALESCE(content, '')) AS content_length
                FROM documents
                ORDER BY id DESC
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def get_document(self, doc_id: int) -> dict[str, Any]:
        with db_session() as conn:
            row = conn.execute(
                """
                SELECT id, filename, content, file_size, file_type, status, error_message, created_at, updated_at
                FROM documents
                WHERE id = ?
                """,
                (doc_id,),
            ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Document ID {doc_id} not found")

        return dict(row)

    def delete_document(self, doc_id: int) -> None:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM documents WHERE id = ?", (doc_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"Document ID {doc_id} not found")

            cursor.execute("DELETE FROM document_chunks WHERE document_id = ?", (doc_id,))
            cursor.execute("DELETE FROM document_jobs WHERE document_id = ?", (doc_id,))
            cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

        bootstrap_rag_store()

    def _extract_text(self, upload: StoredUpload) -> str:
        if upload.file_size > settings.MAX_FILE_SIZE:
            max_size_mb = settings.MAX_FILE_SIZE // 1024 // 1024
            raise HTTPException(status_code=400, detail=f"File exceeds size limit ({max_size_mb}MB)")

        if upload.file_type not in settings.ALLOWED_EXTENSIONS:
            allowed = ", ".join(settings.ALLOWED_EXTENSIONS)
            raise HTTPException(status_code=400, detail=f"Only {allowed} files are supported")

        raw = upload.content_bytes
        if upload.file_type == "txt":
            text = raw.decode("utf-8", errors="ignore")
        elif upload.file_type == "docx":
            document = Document(io.BytesIO(raw))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        elif upload.file_type == "pdf":
            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        cleaned = text.strip()
        if not cleaned:
            raise HTTPException(status_code=400, detail="Document content is empty")
        return cleaned

    def _mark_job_started(self, document_id: int, job_id: int) -> None:
        with db_session() as conn:
            conn.execute(
                """
                UPDATE document_jobs
                SET status = 'running', started_at = datetime('now'), updated_at = datetime('now'), error_message = NULL
                WHERE id = ? AND document_id = ?
                """,
                (job_id, document_id),
            )
            conn.execute(
                """
                UPDATE documents
                SET status = 'processing', error_message = NULL, updated_at = datetime('now')
                WHERE id = ?
                """,
                (document_id,),
            )

    def _mark_job_succeeded(self, document_id: int, job_id: int) -> None:
        with db_session() as conn:
            conn.execute(
                """
                UPDATE document_jobs
                SET status = 'completed', finished_at = datetime('now'), updated_at = datetime('now')
                WHERE id = ? AND document_id = ?
                """,
                (job_id, document_id),
            )
            conn.execute(
                """
                UPDATE documents
                SET status = 'ready', updated_at = datetime('now')
                WHERE id = ?
                """,
                (document_id,),
            )

    def _mark_job_failed(self, document_id: int, job_id: int, error_message: str) -> None:
        with db_session() as conn:
            conn.execute(
                """
                UPDATE document_jobs
                SET status = 'failed', finished_at = datetime('now'), updated_at = datetime('now'), error_message = ?
                WHERE id = ? AND document_id = ?
                """,
                (error_message, job_id, document_id),
            )
            conn.execute(
                """
                UPDATE documents
                SET status = 'failed', error_message = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (error_message, document_id),
            )


def store_upload_file(file: UploadFile) -> StoredUpload:
    filename = file.filename or "uploaded-file"
    file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content_bytes = file.file.read()
    return StoredUpload(
        filename=filename,
        file_type=file_type,
        file_size=len(content_bytes),
        content_bytes=content_bytes,
    )


document_ingestion_service = DocumentIngestionService()
