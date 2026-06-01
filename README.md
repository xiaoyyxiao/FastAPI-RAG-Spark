# FastAPI-RAG-Spark

A small FastAPI-based intelligent Q&A system with:

- FastAPI HTTP APIs
- SQLite document and user storage
- FAISS vector retrieval
- iFLYTEK Spark as the LLM backend

## Quick start

### 1. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Create your local config

```powershell
Copy-Item .env.example .env
```

Update `.env` and set at least:

- `XF_APIKey`
- `XF_APISecret`
- `SECRET_KEY`

`XF_APPID` is kept for completeness, but the current request flow uses `XF_APIKey` and `XF_APISecret`.

### 4. Start the service

```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open:

- Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Root check: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

## Default admin account

On first startup the app creates:

- username: `admin`
- password: `admin123456`

Change it after the first login.

## Suggested first API flow

1. `POST /api/v1/auth/login`
2. `GET /api/v1/docs/list`
3. `POST /api/v1/docs/upload`
4. `POST /api/v1/question/ask`

Example request bodies for `/api/v1/question/ask`:

```json
{
  "question": "什么是 RAG？",
  "mode": "general"
}
```

```json
{
  "question": "总结知识库中的 RAG 定义",
  "mode": "rag",
  "top_k": 3
}
```

```json
{
  "question": "总结这份文档的核心内容",
  "mode": "doc",
  "doc_id": 1
}
```

## Notes

- Redis is currently mocked in `core/redis_client.py`, so a real Redis instance is not required to boot the project.
- The embedding model is loaded lazily. The app can now start even before the local vector model has been downloaded.
- The first document upload may take longer because `sentence-transformers` may need to download `BAAI/bge-small-zh`.
- If `faiss-cpu` or `sentence-transformers` fails to install on Python 3.13, switch to Python 3.10 or 3.11.
