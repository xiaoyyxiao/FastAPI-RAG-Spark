from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_CASES_PATH = ROOT / "eval_dataset" / "qa_cases.jsonl"
DEFAULT_DOCUMENTS_DIR = ROOT / "eval_dataset" / "documents"
DEFAULT_OUTPUT_PATH = ROOT / "eval_dataset" / "last_eval_report.json"
DEFAULT_DOC_FILES = {
    "system_overview": DEFAULT_DOCUMENTS_DIR / "system_overview.docx",
    "llm_and_eval_notes": DEFAULT_DOCUMENTS_DIR / "llm_and_eval_notes.pdf",
    "ingestion_and_ops": DEFAULT_DOCUMENTS_DIR / "ingestion_and_ops.txt",
}


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        cases.append(json.loads(line))
    return cases


def keyword_hit_ratio(answer: str, keywords: list[str]) -> float:
    if not keywords:
        return 0.0
    hit_count = sum(1 for keyword in keywords if keyword.lower() in answer.lower())
    return hit_count / len(keywords)


def upload_eval_document(base_url: str, document_path: Path) -> dict[str, Any]:
    with document_path.open("rb") as file_obj:
        response = requests.post(
            f"{base_url}/api/v1/docs/upload",
            files={"file": (document_path.name, file_obj)},
            timeout=120,
        )
    response.raise_for_status()
    return response.json()["data"]


def wait_until_document_ready(
    base_url: str,
    doc_id: int,
    timeout_seconds: int = 120,
    poll_interval: float = 2.0,
) -> dict[str, Any]:
    started = time.time()
    while time.time() - started < timeout_seconds:
        response = requests.get(f"{base_url}/api/v1/docs/get/{doc_id}", timeout=30)
        response.raise_for_status()
        data = response.json()["data"]
        status = data.get("status")
        if status == "ready":
            return data
        if status == "failed":
            raise RuntimeError(f"Document ingestion failed: {data.get('error_message')}")
        time.sleep(poll_interval)
    raise TimeoutError(f"Document {doc_id} did not become ready within {timeout_seconds} seconds")


def resolve_document_paths(documents_dir: Path) -> dict[str, Path]:
    missing = [name for name, path in DEFAULT_DOC_FILES.items() if not (documents_dir / path.name).exists()]
    if missing:
        missing_names = ", ".join(missing)
        raise FileNotFoundError(f"Missing evaluation documents: {missing_names}")
    return {name: documents_dir / path.name for name, path in DEFAULT_DOC_FILES.items()}


def upload_documents(
    base_url: str,
    documents_dir: Path,
    wait_timeout: int,
) -> dict[str, dict[str, Any]]:
    document_paths = resolve_document_paths(documents_dir)
    uploaded_docs: dict[str, dict[str, Any]] = {}
    for source_doc, path in document_paths.items():
        print(f"Uploading evaluation document [{source_doc}]: {path}")
        upload_info = upload_eval_document(base_url, path)
        doc_id = int(upload_info["document_id"])
        print(f"Uploaded document_id={doc_id}, waiting for ingestion...")
        ready_doc = wait_until_document_ready(base_url, doc_id, timeout_seconds=wait_timeout)
        print(f"Document ready: {ready_doc['filename']} (id={doc_id})")
        uploaded_docs[source_doc] = {
            "source_doc": source_doc,
            "doc_path": str(path),
            "doc_id": doc_id,
            "filename": ready_doc.get("filename"),
            "status": ready_doc.get("status"),
        }
    return uploaded_docs


def prepare_cases(cases: list[dict[str, Any]], uploaded_docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = []
    for case in cases:
        item = dict(case)
        if item.get("mode") == "doc":
            source_doc = item.get("source_doc")
            if not source_doc:
                raise ValueError(f"Doc mode case {item.get('id')} is missing source_doc")
            if source_doc not in uploaded_docs:
                raise KeyError(f"Case {item.get('id')} references unknown source_doc: {source_doc}")
            item["doc_id"] = uploaded_docs[source_doc]["doc_id"]
        prepared.append(item)
    return prepared


def evaluate_case(base_url: str, case: dict[str, Any]) -> dict[str, Any]:
    ask_payload = {
        "question": case["question"],
        "mode": case.get("mode", "rag"),
        "top_k": 3,
        "return_references": True,
        "evaluate_answer": False,
    }
    if case.get("doc_id") is not None:
        ask_payload["doc_id"] = case["doc_id"]

    conversation = case.get("conversation") or []
    conversation_id = None
    for item in conversation:
        followup_payload = {
            "question": item["content"],
            "mode": case.get("mode", "rag"),
            "top_k": 3,
            "return_references": True,
            "evaluate_answer": False,
        }
        if case.get("doc_id") is not None:
            followup_payload["doc_id"] = case["doc_id"]
        if conversation_id is not None:
            followup_payload["conversation_id"] = conversation_id
        response = requests.post(f"{base_url}/api/v1/question/ask", json=followup_payload, timeout=120)
        response.raise_for_status()
        conversation_id = response.json()["data"]["conversation_id"]

    if conversation_id is not None:
        ask_payload["conversation_id"] = conversation_id

    ask_response = requests.post(f"{base_url}/api/v1/question/ask", json=ask_payload, timeout=120)
    ask_response.raise_for_status()
    ask_data = ask_response.json()["data"]

    references = [item.get("text", "") for item in ask_data.get("references", [])]
    eval_payload = {
        "trace_id": ask_data.get("trace_id"),
        "question": case["question"],
        "answer": ask_data["answer"],
        "expected_answer": case.get("expected_answer"),
        "references": references,
    }
    eval_response = requests.post(f"{base_url}/api/v1/question/evaluate", json=eval_payload, timeout=120)
    eval_response.raise_for_status()
    eval_data = eval_response.json()["data"]

    return {
        "id": case["id"],
        "category": case.get("category"),
        "mode": case.get("mode"),
        "source_doc": case.get("source_doc"),
        "doc_id": case.get("doc_id"),
        "question": case["question"],
        "trace_id": ask_data.get("trace_id"),
        "conversation_id": ask_data.get("conversation_id"),
        "provider_name": ask_data.get("provider_name"),
        "answer": ask_data["answer"],
        "expected_answer": case.get("expected_answer"),
        "keyword_hit_ratio": round(keyword_hit_ratio(ask_data["answer"], case.get("keywords", [])), 4),
        "reference_count": len(references),
        "score": eval_data.get("score", 0),
        "verdict": eval_data.get("verdict", "unknown"),
        "groundedness": eval_data.get("groundedness", 0),
        "relevance": eval_data.get("relevance", 0),
        "completeness": eval_data.get("completeness", 0),
        "clarity": eval_data.get("clarity", 0),
        "timings_ms": ask_data.get("timings_ms", {}),
        "retrieval_quality": ask_data.get("retrieval_quality", {}),
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "case_count": 0,
            "avg_score": 0,
            "pass_rate": 0,
            "avg_keyword_hit_ratio": 0,
            "avg_reference_count": 0,
        }

    pass_count = sum(1 for item in results if item.get("verdict") == "pass")
    score_sum = sum(item.get("score", 0) for item in results)
    keyword_ratio_sum = sum(item.get("keyword_hit_ratio", 0) for item in results)
    reference_count_sum = sum(item.get("reference_count", 0) for item in results)

    return {
        "case_count": len(results),
        "avg_score": round(score_sum / len(results), 2),
        "pass_rate": round(pass_count / len(results), 4),
        "avg_keyword_hit_ratio": round(keyword_ratio_sum / len(results), 4),
        "avg_reference_count": round(reference_count_sum / len(results), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local RAG evaluation dataset against the FastAPI service.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL of the running FastAPI service.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH), help="Path to the JSONL evaluation cases.")
    parser.add_argument(
        "--documents-dir",
        default=str(DEFAULT_DOCUMENTS_DIR),
        help="Directory containing evaluation documents to auto-upload.",
    )
    parser.add_argument("--wait-timeout", type=int, default=120, help="Max seconds to wait for uploaded documents.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Path to save the evaluation report JSON.",
    )
    args = parser.parse_args()

    cases_path = Path(args.cases)
    documents_dir = Path(args.documents_dir)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cases = load_cases(cases_path)
    uploaded_docs = upload_documents(args.base_url, documents_dir, args.wait_timeout)
    prepared_cases = prepare_cases(cases, uploaded_docs)
    results = []
    failures = []

    for index, case in enumerate(prepared_cases, start=1):
        print(f"[{index}/{len(prepared_cases)}] Running {case['id']} - {case['question']}")
        try:
            results.append(evaluate_case(args.base_url, case))
        except Exception as exc:
            failures.append(
                {
                    "id": case.get("id"),
                    "question": case.get("question"),
                    "source_doc": case.get("source_doc"),
                    "error": str(exc),
                }
            )

    report = {
        "base_url": args.base_url,
        "cases_path": str(cases_path),
        "documents_dir": str(documents_dir),
        "uploaded_documents": list(uploaded_docs.values()),
        "summary": summarize(results),
        "results": results,
        "failures": failures,
    }

    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Saved report to: {output_path}")
    if failures:
        print(f"Failures: {len(failures)}")


if __name__ == "__main__":
    main()
