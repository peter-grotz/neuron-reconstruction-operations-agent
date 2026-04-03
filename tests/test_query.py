from pathlib import Path

from exaspim_agent.application.ingestion import IngestionService
from exaspim_agent.application.query_service import QueryService
from exaspim_agent.connectors.local_files import LocalJsonConnector
from exaspim_agent.indexing.retriever import KeywordRetriever
from exaspim_agent.llm.simple import RuleBasedSynthesizer
from exaspim_agent.storage.sqlite_store import SQLiteDocumentStore


def _build_query_service(tmp_path: Path) -> QueryService:
    connector = LocalJsonConnector(Path("data/sample/local_records.json"))
    store = SQLiteDocumentStore(tmp_path / "agent.db")
    IngestionService([connector], store, chunk_size=400, chunk_overlap=50).ingest()
    return QueryService(
        retriever=KeywordRetriever(store),
        synthesizer=RuleBasedSynthesizer(),
        default_top_k=5,
    )


def test_query_returns_citations_and_facts(tmp_path: Path) -> None:
    service = _build_query_service(tmp_path)

    response = service.query("Which sample completed annotation but not reconstruction?")

    assert "EXA-001" in response.answer
    assert response.citations
    assert any("reconstruction pending" in fact or "annotation_complete" in fact for fact in response.facts)
