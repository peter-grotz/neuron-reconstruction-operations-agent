from __future__ import annotations

import math
import re
from typing import Optional

from exaspim_agent.domain.models import RetrievalResult
from exaspim_agent.storage.sqlite_store import SQLiteDocumentStore


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]+")


class KeywordRetriever:
    def __init__(self, store: SQLiteDocumentStore) -> None:
        self.store = store

    def search(
        self,
        query: str,
        top_k: int,
        connector_filters: Optional[list[str]] = None,
    ) -> list[RetrievalResult]:
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        results: list[RetrievalResult] = []
        for chunk in self.store.load_chunks(connector_filters=connector_filters):
            chunk_terms = self._tokenize(chunk.text)
            score = self._score(query, query_terms, chunk.text, chunk_terms, chunk.entity_keys, chunk.metadata)
            if score > 0:
                results.append(RetrievalResult(score=score, chunk=chunk))

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token.lower() for token in TOKEN_PATTERN.findall(text)}

    def _score(
        self,
        raw_query: str,
        query_terms: set[str],
        chunk_text: str,
        chunk_terms: set[str],
        entity_keys: list[str],
        metadata: dict[str, object],
    ) -> float:
        overlap = len(query_terms & chunk_terms)
        if overlap == 0:
            return 0.0

        score = overlap / math.sqrt(max(len(chunk_terms), 1))
        lower_chunk = chunk_text.lower()
        lower_query = raw_query.lower()
        if lower_query in lower_chunk:
            score += 2.0

        lower_entities = [item.lower() for item in entity_keys]
        for term in query_terms:
            if term in lower_entities:
                score += 1.5

        for value in metadata.values():
            if isinstance(value, (str, int, float)) and str(value).lower() in lower_query:
                score += 0.75

        return score
