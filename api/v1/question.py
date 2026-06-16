import json
import re
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from core.database import db_session
from services.analytics_service import analytics_service
from services.conversation_service import conversation_service
from services.evaluation_record_service import evaluation_record_service
from services.feedback_service import feedback_service
from services.llm_gateway import llm_gateway
from services.retrieval_service import retrieval_service, tokenize
from services.trace_service import trace_service

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
        "description": "直接调用大模型回答，不依赖知识库。",
        "value": {
            "question": "什么是 FastAPI？",
            "mode": "general",
            "return_references": False,
        },
    },
    "rag": {
        "summary": "知识库检索问答",
        "description": "基于已上传文档检索后再回答。",
        "value": {
            "question": "这个系统支持什么能力？",
            "mode": "rag",
            "top_k": 3,
            "return_references": True,
        },
    },
    "doc": {
        "summary": "指定文档问答",
        "description": "只基于指定文档内容回答。",
        "value": {
            "question": "这个文档提到了什么？",
            "mode": "doc",
            "doc_id": 1,
            "return_references": True,
        },
    },
}


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, description="User question")
    conversation_id: int | None = Field(None, description="Optional conversation ID for multi-turn chat")
    mode: Literal["general", "rag", "doc"] = Field(
        "general",
        description="Answer mode: general uses only the LLM, rag uses retrieved knowledge, doc uses a specific document",
    )
    doc_id: int | None = Field(None, description="Optional document ID")
    top_k: int = Field(3, ge=1, le=10, description="Number of retrieved chunks")
    return_references: bool = Field(True, description="Whether to return retrieved chunks")
    evaluate_answer: bool = Field(False, description="Whether to evaluate the generated answer")


class AnswerEvaluationRequest(BaseModel):
    trace_id: str | None = Field(None, description="Optional trace ID associated with this answer")
    question: str = Field(..., min_length=1, description="Original question")
    answer: str = Field(..., min_length=1, description="Generated answer")
    expected_answer: str | None = Field(None, description="Optional ideal answer")
    references: list[str] = Field(default_factory=list, description="Retrieved context snippets")
    rubric: list[str] = Field(default_factory=lambda: DEFAULT_RUBRIC.copy(), description="Evaluation rubric")


class FeedbackRequest(BaseModel):
    trace_id: str = Field(..., min_length=1, description="Trace ID to attach feedback to")
    rating: Literal["up", "down"] = Field(..., description="User feedback rating")
    comment: str | None = Field(None, description="Optional user comment")


def get_doc_content_by_id(doc_id: int) -> str:
    try:
        with db_session() as conn:
            doc = conn.execute(
                "SELECT content FROM documents WHERE id = ? AND status = 'ready'",
                (doc_id,),
            ).fetchone()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc

    if not doc:
        raise HTTPException(status_code=404, detail=f"Document ID {doc_id} not found")

    return doc["content"]


def build_answer_prompt(question: str, context: str, history_text: str = "") -> str:
    history_block = f"\n最近对话:\n{history_text}\n" if history_text else ""
    return f"""
你是一个企业知识库问答助手。请优先依据提供的上下文回答用户问题。
如果上下文不足，请明确说明哪些信息不确定，不要编造事实。
默认使用与用户提问相同的语言回答；如果用户使用中文提问，请使用简体中文回答。{history_block}
上下文:
{context}

用户问题:
{question}

请给出清晰、准确、易懂的回答。
""".strip()


def build_general_prompt(question: str, history_text: str = "") -> str:
    history_block = f"\n最近对话:\n{history_text}\n" if history_text else ""
    return f"""
你是一个企业智能问答助手。请直接回答下面的问题。
默认使用与用户提问相同的语言回答；如果用户使用中文提问，请使用简体中文回答。{history_block}
用户问题:
{question}
""".strip()


def build_rewrite_prompt(question: str, history: list[dict]) -> str:
    history_lines = [f"{item['role']}: {item['content']}" for item in history]
    history_text = "\n".join(history_lines) if history_lines else "No prior conversation."

    return f"""
You rewrite follow-up user questions into a standalone search query.
If the current question is already standalone, return it unchanged.
Return only the rewritten question with no extra text.

Conversation:
{history_text}

Current question:
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

    raw_result = llm_gateway.ask(eval_prompt)

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


def rewrite_question(question: str, history: list[dict]) -> str:
    if not history:
        return question

    try:
        rewritten = llm_gateway.ask(build_rewrite_prompt(question, history)).strip()
        return rewritten or question
    except Exception:
        return question


def format_history(history: list[dict]) -> str:
    return "\n".join([f"{item['role']}: {item['content']}" for item in history])


def summarize_references(references: list[dict]) -> list[dict]:
    summary = []
    for item in references:
        summary.append(
            {
                "document_id": item.get("document_id"),
                "chunk_index": item.get("chunk_index"),
                "score": item.get("score"),
                "source": item.get("source"),
                "retrieval_type": item.get("retrieval_type"),
                "text_preview": item.get("text", "")[:180],
            }
        )
    return summary


def build_retrieval_quality_summary(question: str, references: list[dict]) -> dict:
    query_tokens = set(tokenize(question))
    reference_token_sets = [set(tokenize(item.get("text", ""))) for item in references if item.get("text")]

    if not query_tokens or not reference_token_sets:
        return {
            "query_token_count": len(query_tokens),
            "hit_count": len(references),
            "avg_query_overlap": 0.0,
            "max_query_overlap": 0.0,
        }

    overlap_ratios = []
    for token_set in reference_token_sets:
        overlap = len(query_tokens & token_set)
        overlap_ratios.append(overlap / max(len(query_tokens), 1))

    return {
        "query_token_count": len(query_tokens),
        "hit_count": len(references),
        "avg_query_overlap": round(sum(overlap_ratios) / len(overlap_ratios), 4),
        "max_query_overlap": round(max(overlap_ratios), 4),
    }


@router.post("/ask", summary="RAG question answering with conversation support")
async def ask_question(
    request: QuestionRequest = Body(..., openapi_examples=QUESTION_REQUEST_EXAMPLES)
):
    trace_id = uuid.uuid4().hex
    total_started = time.perf_counter()

    try:
        conversation = conversation_service.get_or_create_conversation(
            request.conversation_id,
            request.question,
        )
        conversation_id = conversation["id"]
        history = conversation_service.get_recent_history(conversation_id)
        history_text = format_history(history)

        rewrite_started = time.perf_counter()
        rewritten_question = rewrite_question(request.question, history)
        rewrite_latency_ms = int((time.perf_counter() - rewrite_started) * 1000)

        references = []
        answer_mode = request.mode

        retrieval_started = time.perf_counter()
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
                    "document_id": request.doc_id,
                    "chunk_index": 0,
                    "retrieval_type": "doc",
                }
            ]
            prompt = build_answer_prompt(request.question, context, history_text)
        elif request.mode == "rag":
            references = retrieval_service.hybrid_retrieve(rewritten_question, request.top_k)
            if references:
                context = "\n\n".join([item["text"] for item in references])
                prompt = build_answer_prompt(request.question, context, history_text)
            else:
                answer_mode = "general"
                prompt = build_general_prompt(request.question, history_text)
        else:
            prompt = build_general_prompt(request.question, history_text)
        retrieval_latency_ms = int((time.perf_counter() - retrieval_started) * 1000)

        conversation_service.add_message(
            conversation_id=conversation_id,
            role="user",
            content=request.question,
            mode=request.mode,
            doc_id=request.doc_id,
        )

        generation_started = time.perf_counter()
        generation_result = llm_gateway.chat_with_metadata(
            [{"role": "user", "content": prompt}]
        )
        generation_latency_ms = int((time.perf_counter() - generation_started) * 1000)

        answer = generation_result["content"]
        provider_name = generation_result["provider_name"]
        if not answer:
            raise HTTPException(status_code=500, detail="Model returned an empty answer")

        conversation_service.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
            mode=answer_mode,
            doc_id=request.doc_id,
            references=references,
        )

        total_latency_ms = int((time.perf_counter() - total_started) * 1000)
        retrieval_quality = build_retrieval_quality_summary(rewritten_question, references)

        trace_service.create_trace(
            trace_id=trace_id,
            question=request.question,
            rewritten_question=rewritten_question,
            answer_mode=answer_mode,
            conversation_id=conversation_id,
            provider_name=provider_name,
            references=summarize_references(references),
            stage_latencies_ms={
                "rewrite": rewrite_latency_ms,
                "retrieval": retrieval_latency_ms,
                "generation": generation_latency_ms,
                "total": total_latency_ms,
            },
            metadata={
                "requested_mode": request.mode,
                "doc_id": request.doc_id,
                "top_k": request.top_k,
                "history_turns": len(history),
                "return_references": request.return_references,
                "used_fallback": provider_name != "spark",
                "retrieval_quality": retrieval_quality,
            },
        )

        response_data = {
            "trace_id": trace_id,
            "conversation_id": conversation_id,
            "question": request.question,
            "rewritten_question": rewritten_question,
            "mode": answer_mode,
            "provider_name": provider_name,
            "timings_ms": {
                "rewrite": rewrite_latency_ms,
                "retrieval": retrieval_latency_ms,
                "generation": generation_latency_ms,
                "total": total_latency_ms,
            },
            "retrieval_quality": retrieval_quality,
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
            evaluation_record_service.create_evaluation(
                trace_id=trace_id,
                question=request.question,
                answer=answer,
                expected_answer=None,
                evaluation=evaluation,
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
        evaluation_record_service.create_evaluation(
            trace_id=request.trace_id,
            question=request.question,
            answer=request.answer,
            expected_answer=request.expected_answer,
            evaluation=evaluation,
        )
        return {
            "code": 200,
            "msg": "Success",
            "data": evaluation,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {exc}") from exc


@router.post("/feedback", summary="Submit feedback for a QA trace")
async def submit_feedback(request: FeedbackRequest):
    feedback_service.add_feedback(
        trace_id=request.trace_id,
        rating=request.rating,
        comment=request.comment,
    )
    return {
        "code": 200,
        "msg": "Success",
        "data": {
            "trace_id": request.trace_id,
            "rating": request.rating,
            "comment": request.comment,
        },
    }


@router.get("/feedback", summary="List recent user feedback")
async def list_feedback(limit: int = 20):
    return {
        "code": 200,
        "msg": "Success",
        "data": feedback_service.list_feedback(limit),
    }


@router.get("/evaluations", summary="List recent evaluations")
async def list_evaluations(limit: int = 20):
    return {
        "code": 200,
        "msg": "Success",
        "data": evaluation_record_service.list_evaluations(limit),
    }


@router.get("/ops/overview", summary="Operations overview for RAG runtime")
async def get_ops_overview():
    return {
        "code": 200,
        "msg": "Success",
        "data": analytics_service.get_overview(),
    }


@router.get("/ops/evaluations/low-score", summary="List low-score evaluations")
async def get_low_score_evaluations(limit: int = 10, score_threshold: int = 60):
    return {
        "code": 200,
        "msg": "Success",
        "data": analytics_service.list_low_score_evaluations(limit, score_threshold),
    }


@router.get("/ops/traces/fallbacks", summary="List recent fallback traces")
async def get_recent_fallbacks(limit: int = 10):
    return {
        "code": 200,
        "msg": "Success",
        "data": analytics_service.list_recent_fallbacks(limit),
    }


@router.get("/ops/traces/low-overlap", summary="List low-overlap retrieval traces")
async def get_low_overlap_traces(limit: int = 10, overlap_threshold: float = 0.2):
    return {
        "code": 200,
        "msg": "Success",
        "data": analytics_service.list_low_overlap_traces(limit, overlap_threshold),
    }


@router.get("/conversations", summary="List conversations")
async def list_conversations():
    return {
        "code": 200,
        "msg": "Success",
        "data": conversation_service.list_conversations(),
    }


@router.get("/conversations/{conversation_id}", summary="Get conversation messages")
async def get_conversation(conversation_id: int):
    return {
        "code": 200,
        "msg": "Success",
        "data": conversation_service.get_conversation_messages(conversation_id),
    }


@router.get("/llm/health", summary="View LLM provider health")
async def get_llm_health():
    return {
        "code": 200,
        "msg": "Success",
        "data": llm_gateway.health(),
    }


@router.get("/traces", summary="List recent QA traces")
async def list_traces(limit: int = 20):
    return {
        "code": 200,
        "msg": "Success",
        "data": trace_service.list_traces(limit),
    }


@router.get("/traces/{trace_id}", summary="Get a single QA trace")
async def get_trace(trace_id: str):
    trace = trace_service.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace ID {trace_id} not found")

    return {
        "code": 200,
        "msg": "Success",
        "data": trace,
    }
