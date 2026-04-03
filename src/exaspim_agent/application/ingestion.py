from __future__ import annotations

import hashlib

from exaspim_agent.connectors.base import DataConnector
from exaspim_agent.domain.models import (
    DocumentChunk,
    IngestionConnectorReport,
    IngestionReport,
    NormalizedDocument,
    SourceRecord,
)
from exaspim_agent.indexing.chunker import chunk_text
from exaspim_agent.storage.sqlite_store import SQLiteDocumentStore


class IngestionService:
    def __init__(
        self,
        connectors: list[DataConnector],
        store: SQLiteDocumentStore,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        self.connectors = connectors
        self.store = store
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def ingest(self) -> IngestionReport:
        reports: list[IngestionConnectorReport] = []
        total_records = 0
        total_documents = 0
        total_chunks = 0

        for connector in self.connectors:
            records = connector.fetch()
            documents = [self._normalize(record) for record in records]
            chunks = self._chunk_documents(documents)
            self.store.replace_connector_data(connector.name, documents, chunks)

            reports.append(
                IngestionConnectorReport(
                    connector=connector.name,
                    record_count=len(records),
                    document_count=len(documents),
                    chunk_count=len(chunks),
                )
            )
            total_records += len(records)
            total_documents += len(documents)
            total_chunks += len(chunks)

        return IngestionReport(
            total_records=total_records,
            total_documents=total_documents,
            total_chunks=total_chunks,
            connectors=reports,
        )

    def _normalize(self, record: SourceRecord) -> NormalizedDocument:
        fingerprint = hashlib.sha1(f"{record.connector}:{record.record_id}".encode("utf-8")).hexdigest()[:16]
        return NormalizedDocument(
            document_id=f"{record.connector}-{fingerprint}",
            record_id=record.record_id,
            connector=record.connector,
            source_kind=record.source_kind,
            title=record.title,
            text=record.body,
            source_uri=record.source_uri,
            entity_keys=record.entity_keys,
            metadata=record.metadata,
        )

    def _chunk_documents(self, documents: list[NormalizedDocument]) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        for document in documents:
            for index, chunk in enumerate(chunk_text(document.text, self.chunk_size, self.chunk_overlap)):
                chunk_id = f"{document.document_id}-chunk-{index}"
                chunks.append(
                    DocumentChunk(
                        chunk_id=chunk_id,
                        document_id=document.document_id,
                        connector=document.connector,
                        source_kind=document.source_kind,
                        chunk_index=index,
                        text=chunk,
                        source_uri=document.source_uri,
                        title=document.title,
                        entity_keys=document.entity_keys,
                        metadata=document.metadata,
                    )
                )
        return chunks
