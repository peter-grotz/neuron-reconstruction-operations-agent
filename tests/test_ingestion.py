from pathlib import Path

from exaspim_agent.application.ingestion import IngestionService
from exaspim_agent.connectors.local_files import LocalJsonConnector
from exaspim_agent.storage.sqlite_store import SQLiteDocumentStore


def test_ingestion_persists_documents_and_chunks(tmp_path: Path) -> None:
    source_path = Path("data/sample/local_records.json")
    db_path = tmp_path / "agent.db"
    connector = LocalJsonConnector(source_path)
    store = SQLiteDocumentStore(db_path)
    service = IngestionService([connector], store, chunk_size=400, chunk_overlap=50)

    report = service.ingest()

    assert report.total_records == 4
    assert report.total_documents == 4
    assert report.total_chunks >= 4
    assert store.list_sources()[0]["connector"] == "local_json"
