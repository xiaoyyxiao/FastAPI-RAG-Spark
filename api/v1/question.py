import json
import re
import sqlite3
from typing import Literal

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from core.ai.spark_client import spark_client
from core.rag.rag_service import retrieve_docs_with_scores

router = APIRouter()


DEFAULT_RUBRIC = [
    "groundedness: answer should stay consistent with retrieved context",
    "relevance: answer should directly address the user question",
    "completeness: answer should cover the key points needed by the question",
    "clarity: answer should be clear, concise and easy to understand",
]

QUESTION_REQUEST_EXAMPLES = {
    "general": {
        "summary": "通用问答",
        "description": "不依赖知识库，直接调用大模型回答。",
        "value": {
            "question": "问题",
            "mode": "general",
            "return_references": False,
        },
    },
    "rag": {
        "summary": "知识库检索问答",
        "description": "先检索已上传文档，再结合检索结果回答。",
        "value": {
            "question": "问题",
            "mode": "rag",
            "top_k": 3,
            "return_references": True,
        },
    },
    "doc": {
        "summary": "指定文档问答",
        "description": "仅基于指定 doc_id 的文档内容回答。",
        "value": {
            "question": "问题",
            "mode": "doc",
            "doc_id": 1,
            "return_references": True,
        },
    },
}


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, description="User question")
    mode: Literal["general", "rag", "doc"] = Field(
        "general",
        description="Answer mode: general uses only the LLM, rag uses retrieved knowledge, doc uses a specific document",
    )
    doc_id: int | None = Field(None, description="Optional document ID")
    top_k: int = Field(3, ge=1, le=10, description="Number of retrieved chunks")
    return_references: bool = Field(True, description="Whether to return retrieved chunks")
    evaluate_answer: bool = Field(False, description="Whether to evaluate the generated answer")


class AnswerEvaluationRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Original question")
    answer: str = Field(..., min_length=1, description="Generated answer")
    expected_answer: str | None = Field(None, description="Optional ideal answer")
    references: list[str] = Field(default_factory=list, description="Retrieved context snippets")
    rubric: list[str] = Field(default_factory=lambda: DEFAULT_RUBRIC.copy(), description="Evaluation rubric")


def get_doc_content_by_id(doc_id: int) -> str:
    try:
        conn = sqlite3.connect("docs.db")
        cursor = conn.cursor()
        cursor.execute("SELECT content FROM documents WHERE id = ?", (doc_id,))
        doc = cursor.fetchone()
        conn.close()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc

    if not doc:
        raise HTTPException(status_code=404, detail=f"Document ID {doc_id} not found")

    return doc[0]


def build_answer_prompt(question: str, context: str) -> str:
    return f"""
你是一个企业知识库问答助手。
请优先依据提供的上下文回答用户问题。
如果上下文不足，请明确说明哪些信息不确定，不要编造事实。
请默认使用与用户提问相同的语言回答；如果用户使用中文提问，请使用简体中文回答。

上下文:
{context}

用户问题:
{question}

请给出清晰、准确、易懂的回答。
""".strip()


def build_general_prompt(question: str) -> str:
    return f"""
你是一个企业智能问答助手。
请直接回答下面的问题。
请默认使用与用户提问相同的语言回答；如果用户使用中文提问，请使用简体中文回答。

用户问题:
{question}
""".strip()


def extract_json_block(text: str) -> dict:
    fenced_match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if fenced_match:
        return json.loads(fenced_match.group(1))

    direct_match = re.search(r"(\{.*\})", text, re.S)
    if direct_match:
        return json.loads(direct_match.group(1))

    raise ValueError("No JSON object found in evaluation response")


def evaluate_answer_with_llm(
    question: str,
    answer: str,
    references: list[str],
    expected_answer: str | None = None,
    rubric: list[str] | None = None,
) -> dict:
    rubric = rubric or DEFAULT_RUBRIC
    references_text = "\n\n".join(
        [f"Reference {idx + 1}:\n{item}" for idx, item in enumerate(references)]
    ) or "No references were provided."
    expected_text = expected_answer or "No expected answer was provided."
    rubric_text = "\n".join([f"- {item}" for item in rubric])

    eval_prompt = f"""
You are an impartial RAG answer evaluator.
Evaluate the candidate answer using the provided rubric, question, references and expected answer.

Question:
{question}

Candidate Answer:
{answer}

Retrieved References:
{references_text}

Expected Answer:
{expected_text}

Rubric:
{rubric_text}

Return only valid JSON with this schema:
{{
  "verdict": "pass" or "fail",
  "score": integer from 0 to 100,
  "groundedness": integer from 0 to 5,
  "relevance": integer from 0 to 5,
  "completeness": integer from 0 to 5,
  "clarity": integer from 0 to 5,
  "strengths": ["short bullet", "short bullet"],
  "issues": ["short bullet", "short bullet"],
  "suggestions": ["short bullet", "short bullet"],
  "reason": "short paragraph"
}}
""".strip()

    raw_result = spark_client.ask(eval_prompt)

    try:
        parsed = extract_json_block(raw_result)
    except Exception:
        parsed = {
            "verdict": "unknown",
            "score": 0,
            "groundedness": 0,
            "relevance": 0,
            "completeness": 0,
            "clarity": 0,
            "strengths": [],
            "issues": ["The evaluator did not return valid JSON"],
            "suggestions": ["Review the raw evaluation output manually"],
            "reason": raw_result,
        }

    parsed["raw_evaluation"] = raw_result
    return parsed


@router.post("/ask", summary="RAG question answering")
async def ask_question(
    request: QuestionRequest = Body(..., openapi_examples=QUESTION_REQUEST_EXAMPLES)
):
    try:
        references = []
        answer_mode = request.mode

        if request.mode == "doc":
            if request.doc_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="doc mode requires doc_id",
                )
            doc_content = get_doc_content_by_id(request.doc_id)
            context = doc_content
            references = [
                {
                    "rank": 1,
                    "score": 0.0,
                    "text": doc_content[:1200],
                    "source": f"document:{request.doc_id}",
                }
            ]
            prompt = build_answer_prompt(request.question, context)
        elif request.mode == "rag":
            references = retrieve_docs_with_scores(request.question, request.top_k)
            if references:
                context = "\n\n".join([item["text"] for item in references])
                prompt = build_answer_prompt(request.question, context)
            else:
                answer_mode = "general"
                prompt = build_general_prompt(request.question)
        else:
            prompt = build_general_prompt(request.question)

        answer = spark_client.ask(prompt)
        if not answer:
            raise HTTPException(status_code=500, detail="Model returned an empty answer")

        response_data = {
            "question": request.question,
            "mode": answer_mode,
            "answer": answer,
        }

        if request.return_references:
            response_data["references"] = references

        if request.evaluate_answer:
            evaluation = evaluate_answer_with_llm(
                question=request.question,
                answer=answer,
                references=[item["text"] for item in references],
            )
            response_data["evaluation"] = evaluation

        return {
            "code": 200,
            "msg": "Success",
            "data": response_data,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Question answering failed: {exc}") from exc


@router.post("/evaluate", summary="Evaluate an answer with RAG-style rubric")
async def evaluate_answer(request: AnswerEvaluationRequest):
    try:
        evaluation = evaluate_answer_with_llm(
            question=request.question,
            answer=request.answer,
            references=request.references,
            expected_answer=request.expected_answer,
            rubric=request.rubric,
        )
        return {
            "code": 200,
            "msg": "Success",
            "data": evaluation,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {exc}") from exc
