"""Live tools that talk to external systems at call time.

These differ from the knowledge tools in tools.py: those read the local index,
these make network calls to Code Ocean and the morphology portal. They are
registered only when the relevant credentials resolve, so an unconfigured
deployment simply does not expose them.
"""
from __future__ import annotations

from typing import Any

from exaspim_agent.connectors.code_ocean import CodeOceanClient, classify_run
from exaspim_agent.connectors.morphology_portal import MorphologyPortalClient
from exaspim_agent.domain.models import ToolDefinition, ToolExecutionResult


class CodeOceanStatusTool:
    """Read a computation's status and reduce it to an honest verdict.

    Exposes the raw status fields alongside the verdict because no single field
    is trustworthy on its own — a terminated machine can report completed /
    exit 0 / succeeded while having synced nothing.
    """

    definition = ToolDefinition(
        name="code_ocean_run_status",
        description=(
            "Get the status of a Code Ocean computation by id, with a verdict that "
            "accounts for the terminated-machine failure mode (has_results == false "
            "is treated as failure)."
        ),
        input_schema={
            "type": "object",
            "properties": {"computation_id": {"type": "string"}},
            "required": ["computation_id"],
        },
    )

    def __init__(self, client: CodeOceanClient) -> None:
        self.client = client

    def run(self, payload: dict[str, Any]) -> ToolExecutionResult:
        comp = self.client.get_computation(payload["computation_id"])
        return ToolExecutionResult(
            tool_name=self.definition.name,
            output={
                "computation_id": payload["computation_id"],
                "verdict": classify_run(comp),
                "state": comp.get("state"),
                "end_status": comp.get("end_status"),
                "exit_code": comp.get("exit_code"),
                "has_results": comp.get("has_results"),
                "run_time_s": comp.get("run_time"),
                "name": comp.get("name"),
            },
        )


class CodeOceanLaunchTool:
    """Launch a computation. Registered only when launching is explicitly enabled.

    Kept behind a config flag rather than always-on because this is the one tool
    here that spends money and mutates the deployment; a read-only default is the
    safe posture for an operations agent.
    """

    definition = ToolDefinition(
        name="code_ocean_launch_run",
        description=(
            "Launch a Code Ocean computation. Body takes capsule_id (or pipeline_id), "
            "optional ordered `parameters` (plain strings), `named_parameters` "
            "([{param_name, value}]), and `data_assets` ([{id, mount}]). Only available "
            "when the deployment has opted into launching."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "capsule_id": {"type": "string"},
                "pipeline_id": {"type": "string"},
                "parameters": {"type": "array", "items": {"type": "string"}},
                "named_parameters": {"type": "array", "items": {"type": "object"}},
                "data_assets": {"type": "array", "items": {"type": "object"}},
            },
        },
    )

    def __init__(self, client: CodeOceanClient) -> None:
        self.client = client

    def run(self, payload: dict[str, Any]) -> ToolExecutionResult:
        body = {k: v for k, v in payload.items() if v is not None}
        if not body.get("capsule_id") and not body.get("pipeline_id"):
            raise ValueError("code_ocean_launch_run requires capsule_id or pipeline_id")
        result = self.client.launch_computation(body)
        return ToolExecutionResult(
            tool_name=self.definition.name,
            output={"computation_id": result.get("id"), "state": result.get("state"), "raw": result},
        )


class MorphologyPortalQueryTool:
    """Run a read-only GraphQL query against the morphology portal.

    Deliberately query-only. Portal mutations (createSpecimen, importSomas,
    deleteSpecimen, …) exist but write to shared, user-visible data, so they are
    left to a human running the nmcp-portal-api skill directly rather than being
    exposed as agent tools.
    """

    definition = ToolDefinition(
        name="morphology_portal_query",
        description=(
            "Run a read-only GraphQL query against the Neuron Morphology Community "
            "Portal. Provide `query` and optional `variables`. Use for specimen and "
            "neuron/soma lookups; mutations are intentionally not supported here."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "variables": {"type": "object"},
            },
            "required": ["query"],
        },
    )

    #: Cheap guard against a query string that carries a mutation.
    def __init__(self, client: MorphologyPortalClient) -> None:
        self.client = client

    def run(self, payload: dict[str, Any]) -> ToolExecutionResult:
        query = payload["query"]
        if query.lstrip().lower().startswith("mutation"):
            raise ValueError(
                "morphology_portal_query is read-only; run mutations by hand via the "
                "nmcp-portal-api skill."
            )
        result = self.client.query(query, payload.get("variables"))
        return ToolExecutionResult(tool_name=self.definition.name, output=result)
