from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import sqlite3
import requests
from core.ai.spark_client import spark_client
from core.rag.rag_service import retrieve_docs

router = APIRouter()

# ===================== Pydantic模型 =====================
class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, description="用户的问题")
    doc_id: int | None = Field(None, description="可选：指定文档ID")

# ===================== 数据库工具函数 =====================
def get_doc_content_by_id(doc_id: int) -> str:
    """根据文档ID获取文档内容"""

    try:
        conn = sqlite3.connect("docs.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT content FROM documents WHERE id = ?",
            (doc_id,)
        )
        doc = cursor.fetchone()
        conn.close()

        if not doc:
            raise HTTPException(
                status_code=404,
                detail=f"文档ID {doc_id} 不存在"
            )

        return doc[0]

    except sqlite3.Error as e:
        raise HTTPException(
            status_code=500,
            detail=f"数据库错误：{str(e)}"
        )

# ===================== AI问答接口 =====================

# ===================== AI问答接口 =====================

@router.post("/ask", summary="RAG智能问答")
async def ask_question(request: QuestionRequest):
    try:
        # ===================== 1 指定文档问答 =====================
        if request.doc_id:
            doc_content = get_doc_content_by_id(request.doc_id)
            prompt = f"""
你是一名企业知识库助手。请优先根据提供的文档内容回答问题。如果文档中没有相关信息，请结合你的通用知识回答。

文档内容：
{doc_content}

用户问题：
{request.question}

请给出准确简洁的回答。
"""

        # ===================== 2 RAG检索问答 (带通用大模型兜底) =====================
        else:
            docs = retrieve_docs(request.question)
            
            if docs:
                # 检索到了内容：让大模型结合知识库回答
                context = "\n".join(docs)
                prompt = f"""
你是一名企业知识库助手。请优先根据以下知识内容回答用户问题。如果提供的知识内容无法回答该问题（例如用户在打招呼或闲聊），请使用你的通用知识进行回复。

知识内容：
{context}

用户问题：
{request.question}

请给出准确、简洁的回答。
"""
            else:
                # 【关键修改】没检索到内容（如闲聊、知识库为空）：直接走通用对话
                prompt = f"""
你是一名企业知识库助手。请回答用户的以下问题：

用户问题：
{request.question}
"""

        # ===================== 3 调用 Spark Lite =====================
        ai_answer = spark_client.ask(prompt)
        if not ai_answer:
            raise HTTPException(
                status_code=500,
                detail="AI未返回有效回答"
            )

        # ===================== 4 返回结果 =====================
        return {
            "code": 200,
            "msg": "查询成功",
            "data": {
                "question": request.question,
                "answer": ai_answer
            }
        }

    # ===================== 异常处理 =====================
    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504,
            detail="AI服务请求超时"
        )

    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail="无法连接AI服务"
        )

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI问答失败：{str(e)}"
        )