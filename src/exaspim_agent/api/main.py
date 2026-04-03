from __future__ import annotations

from functools import lru_cache
from typing import Any
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from exaspim_agent.application.bootstrap import ServiceContainer, build_container
from exaspim_agent.config import get_settings
from exaspim_agent.domain.models import IngestionReport, QueryResponse, ToolDefinition, ToolExecutionResult


class QueryRequest(BaseModel):
    query: str
    top_k: Optional[int] = None
    connector_filters: Optional[list[str]] = None


class ToolPayload(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


@lru_cache(maxsize=1)
def get_container() -> ServiceContainer:
    return build_container(get_settings())


app = FastAPI(title="ExA-SPIM Operations Agent", version="0.1.0")


@app.on_event("startup")
def startup_ingest_if_empty() -> None:
    container = get_container()
    if not container.store.list_sources() and container.connectors:
        container.ingestion_service.ingest()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/sources")
def sources() -> dict[str, object]:
    container = get_container()
    return {"sources": container.store.list_sources()}


@app.get("/tools", response_model=list[ToolDefinition])
def tools() -> list[ToolDefinition]:
    container = get_container()
    return container.tool_registry.list_definitions()


@app.post("/ingest", response_model=IngestionReport)
def ingest() -> IngestionReport:
    container = get_container()
    return container.ingestion_service.ingest()


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    container = get_container()
    return container.query_service.query(
        query=request.query,
        top_k=request.top_k,
        connector_filters=request.connector_filters,
    )


@app.post("/tools/{tool_name}", response_model=ToolExecutionResult)
def run_tool(tool_name: str, request: ToolPayload) -> ToolExecutionResult:
    container = get_container()
    try:
        return container.tool_registry.run(tool_name, request.payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
