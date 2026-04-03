from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceKind(str, Enum):
    SMARTSHEET = "smartsheet"
    TEAMS = "teams"
    S3 = "s3"
    LOCAL_JSON = "local_json"
    MANUAL = "manual"


class SourceRecord(BaseModel):
    record_id: str
    connector: str
    source_kind: SourceKind
    title: str
    body: str
    source_uri: str
    entity_keys: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    read_only: bool = True


class NormalizedDocument(BaseModel):
    document_id: str
    record_id: str
    connector: str
    source_kind: SourceKind
    title: str
    text: str
    source_uri: str
    entity_keys: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentChunk(BaseModel):
    chunk_id: str
    document_id: str
    connector: str
    source_kind: SourceKind
    chunk_index: int
    text: str
    source_uri: str
    title: str
    entity_keys: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    score: float
    chunk: DocumentChunk


class Citation(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    connector: str
    source_uri: str
    excerpt: str


class QueryResponse(BaseModel):
    query: str
    answer: str
    facts: list[str] = Field(default_factory=list)
    derived_metrics: list[str] = Field(default_factory=list)
    inferences: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class IngestionConnectorReport(BaseModel):
    connector: str
    record_count: int
    document_count: int
    chunk_count: int


class IngestionReport(BaseModel):
    total_records: int
    total_documents: int
    total_chunks: int
    connectors: list[IngestionConnectorReport] = Field(default_factory=list)


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolExecutionResult(BaseModel):
    tool_name: str
    output: dict[str, Any]
