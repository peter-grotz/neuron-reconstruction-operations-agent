from __future__ import annotations

from typing import Any, Protocol

from exaspim_agent.domain.models import ToolDefinition, ToolExecutionResult
from exaspim_agent.storage.sqlite_store import SQLiteDocumentStore


class Tool(Protocol):
    definition: ToolDefinition

    def run(self, payload: dict[str, Any]) -> ToolExecutionResult:
        ...


class SearchKnowledgeTool:
    definition = ToolDefinition(
        name="search_knowledge",
        description="Search indexed chunks across connected read-only knowledge sources.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}}},
    )

    def __init__(self, query_service: Any) -> None:
        self.query_service = query_service

    def run(self, payload: dict[str, Any]) -> ToolExecutionResult:
        response = self.query_service.query(payload["query"], top_k=payload.get("top_k"))
        return ToolExecutionResult(tool_name=self.definition.name, output=response.model_dump())


class GetEntityContextTool:
    definition = ToolDefinition(
        name="get_entity_context",
        description="Retrieve all indexed chunk contexts that explicitly match a sample, project, or genotype key.",
        input_schema={"type": "object", "properties": {"entity_key": {"type": "string"}}},
    )

    def __init__(self, store: SQLiteDocumentStore) -> None:
        self.store = store

    def run(self, payload: dict[str, Any]) -> ToolExecutionResult:
        chunks = self.store.load_chunks_for_entity(payload["entity_key"])
        return ToolExecutionResult(
            tool_name=self.definition.name,
            output={
                "entity_key": payload["entity_key"],
                "matches": [
                    {
                        "title": chunk.title,
                        "source_uri": chunk.source_uri,
                        "connector": chunk.connector,
                        "text": chunk.text,
                        "metadata": chunk.metadata,
                    }
                    for chunk in chunks
                ],
            },
        )


class ListSourcesTool:
    definition = ToolDefinition(
        name="list_sources",
        description="List currently indexed source connectors and document counts.",
        input_schema={"type": "object", "properties": {}},
    )

    def __init__(self, store: SQLiteDocumentStore) -> None:
        self.store = store

    def run(self, payload: dict[str, Any]) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.definition.name, output={"sources": self.store.list_sources()})


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.definition.name: tool for tool in tools}

    def list_definitions(self) -> list[ToolDefinition]:
        return [tool.definition for tool in self._tools.values()]

    def run(self, tool_name: str, payload: dict[str, Any]) -> ToolExecutionResult:
        if tool_name not in self._tools:
            raise KeyError(f"Unknown tool: {tool_name}")
        return self._tools[tool_name].run(payload)
