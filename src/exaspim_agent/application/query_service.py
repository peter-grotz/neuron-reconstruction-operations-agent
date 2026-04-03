from __future__ import annotations

from typing import Optional

from exaspim_agent.domain.models import QueryResponse
from exaspim_agent.indexing.retriever import KeywordRetriever
from exaspim_agent.llm.simple import RuleBasedSynthesizer


class QueryService:
    def __init__(
        self,
        retriever: KeywordRetriever,
        synthesizer: RuleBasedSynthesizer,
        default_top_k: int,
    ) -> None:
        self.retriever = retriever
        self.synthesizer = synthesizer
        self.default_top_k = default_top_k

    def query(
        self,
        query: str,
        top_k: Optional[int] = None,
        connector_filters: Optional[list[str]] = None,
    ) -> QueryResponse:
        results = self.retriever.search(
            query=query,
            top_k=top_k or self.default_top_k,
            connector_filters=connector_filters,
        )
        return self.synthesizer.synthesize(query, results)
