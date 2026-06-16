from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from core.database import db_session
from core.rag.rag_service import retrieve_docs_with_scores


TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9_]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


class RetrievalService:
    def hybrid_retrieve(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        dense_candidates = self._dense_retrieve(query, top_k=max(top_k * 2, 6))
        sparse_candidates = self._sparse_retrieve(query, top_k=max(top_k * 2, 6))

        merged = self._merge_candidates(query, dense_candidates, sparse_candidates)
        reranked = self._rerank(query, merged)

        final_results = []
        for index, item in enumerate(reranked[:top_k], start=1):
            final_item = dict(item)
            final_item["rank"] = index
            final_item["score"] = round(final_item.get("final_score", 0.0), 6)
            final_results.append(final_item)

        return final_results

    def _dense_retrieve(self, query: str, top_k: int) -> list[dict[str, Any]]:
        results = retrieve_docs_with_scores(query, top_k)
        normalized = []

        for item in results:
            dense_distance = float(item.get("score", 0.0))
            dense_score = 1.0 / (1.0 + max(dense_distance, 0.0))
            normalized.append(
                {
                    **item,
                    "retrieval_type": "dense",
                    "dense_score": dense_score,
                    "sparse_score": 0.0,
                    "keyword_overlap": 0,
                }
            )

        return normalized

    def _sparse_retrieve(self, query: str, top_k: int) -> list[dict[str, Any]]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        query_counts = Counter(query_tokens)
        results = []

        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT document_id, chunk_index, chunk_text
                FROM document_chunks
                ORDER BY id ASC
                """
            ).fetchall()

        for row in rows:
            chunk_text = row["chunk_text"]
            chunk_tokens = tokenize(chunk_text)
            if not chunk_tokens:
                continue

            chunk_counts = Counter(chunk_tokens)
            overlap = sum(min(chunk_counts[token], count) for token, count in query_counts.items())
            if overlap <= 0:
                continue

            length_penalty = math.log(len(chunk_tokens) + 5, 2)
            sparse_score = overlap / max(length_penalty, 1.0)

            results.append(
                {
                    "text": chunk_text,
                    "source": f"document:{row['document_id']}",
                    "document_id": row["document_id"],
                    "chunk_index": row["chunk_index"],
                    "retrieval_type": "sparse",
                    "dense_score": 0.0,
                    "sparse_score": sparse_score,
                    "keyword_overlap": overlap,
                }
            )

        results.sort(key=lambda item: (item["sparse_score"], item["keyword_overlap"]), reverse=True)
        return results[:top_k]

    def _merge_candidates(
        self,
        query: str,
        dense_candidates: list[dict[str, Any]],
        sparse_candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[tuple[Any, Any], dict[str, Any]] = {}

        for item in dense_candidates + sparse_candidates:
            key = (
                item.get("document_id"),
                item.get("chunk_index"),
            )
            existing = merged.get(key)
            if existing is None:
                merged[key] = dict(item)
                continue

            existing["dense_score"] = max(existing.get("dense_score", 0.0), item.get("dense_score", 0.0))
            existing["sparse_score"] = max(existing.get("sparse_score", 0.0), item.get("sparse_score", 0.0))
            existing["keyword_overlap"] = max(existing.get("keyword_overlap", 0), item.get("keyword_overlap", 0))

            types = {existing.get("retrieval_type", ""), item.get("retrieval_type", "")} - {""}
            existing["retrieval_type"] = "+".join(sorted(types))

            if len(item.get("text", "")) > len(existing.get("text", "")):
                existing["text"] = item["text"]

        query_tokens = set(tokenize(query))
        for item in merged.values():
            chunk_tokens = set(tokenize(item.get("text", "")))
            item["token_jaccard"] = self._jaccard(query_tokens, chunk_tokens)

        return list(merged.values())

    def _rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        query_tokens = set(tokenize(query))

        for item in candidates:
            text = item.get("text", "")
            chunk_tokens = set(tokenize(text))
            lexical_bonus = self._jaccard(query_tokens, chunk_tokens)
            retrieval_bonus = 0.08 if "+" in item.get("retrieval_type", "") else 0.0

            final_score = (
                item.get("dense_score", 0.0) * 0.55
                + item.get("sparse_score", 0.0) * 0.30
                + lexical_bonus * 0.15
                + retrieval_bonus
            )

            item["final_score"] = final_score

        return sorted(
            candidates,
            key=lambda item: (
                item.get("final_score", 0.0),
                item.get("keyword_overlap", 0),
                item.get("dense_score", 0.0),
            ),
            reverse=True,
        )

    def _jaccard(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        intersection = len(left & right)
        union = len(left | right)
        if union == 0:
            return 0.0
        return intersection / union


retrieval_service = RetrievalService()
