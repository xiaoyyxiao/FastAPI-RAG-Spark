from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from core.database import db_session
from services.document_ingestion import (
    document_ingestion_service,
    store_upload_file,
)
from utils.password_utils import verify_password

router = APIRouter()


@router.post("/upload", summary="Upload a document for background ingestion")
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    stored_upload = store_upload_file(file)

    try:
        document_id, job_id = document_ingestion_service.create_document(stored_upload)
        background_tasks.add_task(
            document_ingestion_service.ingest_document,
            document_id,
            job_id,
            stored_upload,
        )
        return {
            "code": 200,
            "msg": "Document upload accepted",
            "data": {
                "document_id": document_id,
                "job_id": job_id,
                "filename": stored_upload.filename,
                "file_type": stored_upload.file_type,
                "file_size": stored_upload.file_size,
                "status": "pending",
            },
        }
    finally:
        await file.close()


@router.get("/list", summary="List uploaded documents")
async def list_documents():
    documents = document_ingestion_service.list_documents()
    return {
        "code": 200,
        "msg": "Success",
        "data": documents,
    }


@router.delete("/delete/{doc_id}", summary="Delete a document, admin only")
async def delete_document(doc_id: int, admin_username: str, admin_password: str):
    with db_session() as conn:
        admin = conn.execute(
            "SELECT password, role FROM user_info WHERE username = ?",
            (admin_username,),
        ).fetchone()

    if not admin:
        raise HTTPException(status_code=401, detail="Admin user does not exist")
    if admin["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete documents")
    if not verify_password(admin_password, admin["password"]):
        raise HTTPException(status_code=401, detail="Admin password is incorrect")

    document_ingestion_service.delete_document(doc_id)
    return {
        "code": 200,
        "msg": f"Document ID {doc_id} deleted successfully",
        "data": {"doc_id": doc_id},
    }


@router.get("/get/{doc_id}", summary="Get a single document")
async def get_document(doc_id: int):
    document = document_ingestion_service.get_document(doc_id)
    return {
        "code": 200,
        "msg": "Success",
        "data": document,
    }
