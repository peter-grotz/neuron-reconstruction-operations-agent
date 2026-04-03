from __future__ import annotations

from dataclasses import dataclass

from exaspim_agent.application.ingestion import IngestionService
from exaspim_agent.application.query_service import QueryService
from exaspim_agent.application.tools import GetEntityContextTool, ListSourcesTool, SearchKnowledgeTool, ToolRegistry
from exaspim_agent.config import Settings
from exaspim_agent.connectors.base import DataConnector
from exaspim_agent.connectors.local_files import LocalJsonConnector
from exaspim_agent.connectors.s3 import S3Connector
from exaspim_agent.connectors.smartsheet import SmartsheetConnector
from exaspim_agent.connectors.teams import TeamsConnector
from exaspim_agent.indexing.retriever import KeywordRetriever
from exaspim_agent.llm.simple import RuleBasedSynthesizer
from exaspim_agent.storage.sqlite_store import SQLiteDocumentStore


@dataclass
class ServiceContainer:
    settings: Settings
    connectors: list[DataConnector]
    store: SQLiteDocumentStore
    ingestion_service: IngestionService
    query_service: QueryService
    tool_registry: ToolRegistry


def build_container(settings: Settings) -> ServiceContainer:
    connectors: list[DataConnector] = []
    if settings.local_json_path:
        connectors.append(LocalJsonConnector(settings.local_json_path))

    smartsheet_token = settings.resolve_smartsheet_token()
    smartsheet_sheets = settings.effective_smartsheet_sheets()
    if smartsheet_token and smartsheet_sheets:
        connectors.append(
            SmartsheetConnector(
                api_token=smartsheet_token,
                sheets=smartsheet_sheets,
                api_base_url=settings.smartsheet_api_base_url,
                integration_source=settings.smartsheet_integration_source,
            )
        )

    teams_secret = settings.resolve_teams_client_secret()
    if settings.teams_tenant_id and settings.teams_client_id and teams_secret and settings.teams_channels:
        connectors.append(
            TeamsConnector(
                tenant_id=settings.teams_tenant_id,
                client_id=settings.teams_client_id,
                client_secret=teams_secret,
                channels=settings.teams_channels,
                graph_base_url=settings.teams_graph_base_url,
                authority_url=settings.teams_authority_url,
                scope=settings.teams_scope,
                max_messages_per_channel=settings.teams_max_messages_per_channel,
            )
        )

    if settings.s3_bucket and settings.s3_prefixes:
        connectors.append(
            S3Connector(
                bucket=settings.s3_bucket,
                prefixes=settings.s3_prefixes,
                region=settings.aws_region,
                max_objects_per_prefix=settings.s3_max_objects_per_prefix,
            )
        )

    store = SQLiteDocumentStore(settings.sqlite_path)
    query_service = QueryService(
        retriever=KeywordRetriever(store),
        synthesizer=RuleBasedSynthesizer(),
        default_top_k=settings.retrieval_top_k,
    )
    tool_registry = ToolRegistry(
        tools=[
            SearchKnowledgeTool(query_service),
            GetEntityContextTool(store),
            ListSourcesTool(store),
        ]
    )
    ingestion_service = IngestionService(
        connectors=connectors,
        store=store,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    return ServiceContainer(
        settings=settings,
        connectors=connectors,
        store=store,
        ingestion_service=ingestion_service,
        query_service=query_service,
        tool_registry=tool_registry,
    )
