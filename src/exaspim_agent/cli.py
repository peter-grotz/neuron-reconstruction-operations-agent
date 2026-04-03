from __future__ import annotations

import json

import typer

from exaspim_agent.application.bootstrap import build_container
from exaspim_agent.config import get_settings

app = typer.Typer(help="ExA-SPIM operations agent CLI")


def _container():
    return build_container(get_settings())


@app.command()
def ingest() -> None:
    """Ingest records from configured read-only connectors."""
    report = _container().ingestion_service.ingest()
    typer.echo(report.model_dump_json(indent=2))


@app.command()
def query(question: str, top_k: int = 6) -> None:
    """Run a local query against the indexed knowledge base."""
    response = _container().query_service.query(question, top_k=top_k)
    typer.echo(response.answer)
    typer.echo("\nCitations:")
    typer.echo(json.dumps([citation.model_dump() for citation in response.citations], indent=2))


@app.command("list-sources")
def list_sources() -> None:
    """List indexed source connectors."""
    typer.echo(json.dumps(_container().store.list_sources(), indent=2))


@app.command()
def tools() -> None:
    """List MCP-style tool definitions."""
    container = _container()
    typer.echo(json.dumps([tool.model_dump() for tool in container.tool_registry.list_definitions()], indent=2))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the FastAPI service."""
    import uvicorn

    uvicorn.run("exaspim_agent.api.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
