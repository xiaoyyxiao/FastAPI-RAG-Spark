from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import dashboard
from api.v1 import auth, docs, question
from config.settings import settings
from core.database import init_db
from core.rag.bootstrap import bootstrap_rag_store


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    bootstrap_rag_store()
    yield


app = FastAPI(title=settings.APP_TITLE, version=settings.APP_VERSION, lifespan=lifespan)

app.include_router(dashboard.router, tags=["运营看板"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["认证"])
app.include_router(docs.router, prefix="/api/v1/docs", tags=["文档管理"])
app.include_router(question.router, prefix="/api/v1/question", tags=["智能问答"])


@app.get("/")
def root():
    return {"msg": f"{settings.APP_TITLE} is running. Visit /docs for API documentation."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
