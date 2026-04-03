from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from exaspim_agent.domain.models import DocumentChunk, NormalizedDocument, SourceKind


class SQLiteDocumentStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    record_id TEXT NOT NULL,
                    connector TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source_uri TEXT NOT NULL,
                    entity_keys_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    connector TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source_uri TEXT NOT NULL,
                    entity_keys_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(document_id)
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_connector ON chunks(connector);
                CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
                """
            )

    def replace_connector_data(
        self,
        connector: str,
        documents: list[NormalizedDocument],
        chunks: list[DocumentChunk],
    ) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM chunks WHERE connector = ?", (connector,))
            connection.execute("DELETE FROM documents WHERE connector = ?", (connector,))
            connection.executemany(
                """
                INSERT INTO documents (
                    document_id, record_id, connector, source_kind, title, text,
                    source_uri, entity_keys_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        document.document_id,
                        document.record_id,
                        document.connector,
                        document.source_kind.value,
                        document.title,
                        document.text,
                        document.source_uri,
                        json.dumps(document.entity_keys),
                        json.dumps(document.metadata, sort_keys=True),
                    )
                    for document in documents
                ],
            )
            connection.executemany(
                """
                INSERT INTO chunks (
                    chunk_id, document_id, connector, source_kind, chunk_index, title,
                    text, source_uri, entity_keys_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.connector,
                        chunk.source_kind.value,
                        chunk.chunk_index,
                        chunk.title,
                        chunk.text,
                        chunk.source_uri,
                        json.dumps(chunk.entity_keys),
                        json.dumps(chunk.metadata, sort_keys=True),
                    )
                    for chunk in chunks
                ],
            )

    def load_chunks(self, connector_filters: Optional[list[str]] = None) -> list[DocumentChunk]:
        query = """
            SELECT chunk_id, document_id, connector, source_kind, chunk_index, title,
                   text, source_uri, entity_keys_json, metadata_json
            FROM chunks
        """
        params: tuple[object, ...] = ()
        if connector_filters:
            placeholders = ", ".join("?" for _ in connector_filters)
            query += f" WHERE connector IN ({placeholders})"
            params = tuple(connector_filters)

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_chunk(row) for row in rows]

    def list_sources(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT connector, source_kind, COUNT(*) AS document_count
                FROM documents
                GROUP BY connector, source_kind
                ORDER BY connector
                """
            ).fetchall()
        return [
            {
                "connector": row["connector"],
                "source_kind": row["source_kind"],
                "document_count": row["document_count"],
            }
            for row in rows
        ]

    def load_chunks_for_entity(self, entity_key: str) -> list[DocumentChunk]:
        entity_key_lower = entity_key.lower()
        matches: list[DocumentChunk] = []
        for chunk in self.load_chunks():
            entity_keys = [item.lower() for item in chunk.entity_keys]
            metadata_values = [str(value).lower() for value in chunk.metadata.values()]
            if entity_key_lower in entity_keys or entity_key_lower in metadata_values:
                matches.append(chunk)
        return matches

    @staticmethod
    def _row_to_chunk(row: sqlite3.Row) -> DocumentChunk:
        return DocumentChunk(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            connector=row["connector"],
            source_kind=SourceKind(row["source_kind"]),
            chunk_index=row["chunk_index"],
            title=row["title"],
            text=row["text"],
            source_uri=row["source_uri"],
            entity_keys=json.loads(row["entity_keys_json"]),
            metadata=json.loads(row["metadata_json"]),
        )
