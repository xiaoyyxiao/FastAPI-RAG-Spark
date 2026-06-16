from core.database import db_session
from core.rag.rag_service import add_document_to_rag
from core.rag.vector_store import vector_store


def bootstrap_rag_store() -> None:
    vector_store.clear()

    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, content
            FROM documents
            WHERE status = 'ready' AND content IS NOT NULL AND TRIM(content) != ''
            ORDER BY id ASC
            """
        ).fetchall()

    for row in rows:
        add_document_to_rag(text=row["content"], document_id=row["id"])
