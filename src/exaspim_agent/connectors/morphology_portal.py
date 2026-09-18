from __future__ import annotations

import json
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from exaspim_agent.connectors.base import DataConnector
from exaspim_agent.domain.models import SourceKind, SourceRecord


class MorphologyPortalClient:
    """Read/query client for the Neuron Morphology Community Portal GraphQL API.

    Auth is a *raw* ``Authorization: <token>`` header. Sending ``Bearer <token>``
    is accepted and silently ignored, leaving the caller anonymous — so a token
    that "works" should be confirmed with ``{ user { id permissions } }``
    returning a non-zero ``permissions`` bitmask.

    Introspection is disabled on the deployment; the authoritative list of
    operations is the portal's own frontend bundle, captured in the
    ``nmcp-portal-api`` skill.
    """

    def __init__(self, base_url: str, token: Optional[str] = None, timeout: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def query(self, query: str, variables: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", "User-Agent": "exaspim-ops-agent"}
        if self.token:
            headers["Authorization"] = self.token  # raw, never "Bearer <token>"
        body = json.dumps({"query": query, "variables": variables or {}}).encode()
        req = Request(self.base_url, data=body, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            # GraphQL errors come back as HTTP 400 with a normal body — read it.
            payload = exc.read().decode("utf-8", errors="replace")
        return json.loads(payload)

    def whoami(self) -> dict[str, Any]:
        return self.query("{ user { id permissions } }")


SPECIMENS_QUERY = """
{ specimens { totalCount items {
    id label collectionId neuronCount referenceDate
    genotype { id name }
    collection { id name }
} } }
"""


class MorphologyPortalConnector(DataConnector):
    """Read-only ingestion of portal specimens (one indexed record per specimen).

    Lets the agent answer "is sample <label> on the portal, and how many somas
    does it carry" from the index. Neuron-level detail stays behind the live
    query tool rather than being bulk-indexed — a specimen can hold thousands of
    somas and indexing them all would swamp the store.
    """

    name = "morphology_portal"

    def __init__(
        self,
        client: MorphologyPortalClient,
        collection_filter: Optional[str] = None,
        max_specimens: int = 500,
    ) -> None:
        self.client = client
        self.collection_filter = collection_filter
        self.max_specimens = max_specimens

    def fetch(self) -> list[SourceRecord]:
        try:
            result = self.client.query(SPECIMENS_QUERY)
        except (HTTPError, URLError, ValueError) as exc:
            raise RuntimeError(f"Morphology portal query failed: {exc}") from exc

        if result.get("errors"):
            messages = "; ".join(e.get("message", "") for e in result["errors"])
            raise RuntimeError(f"Morphology portal returned errors: {messages}")

        items = (result.get("data") or {}).get("specimens", {}).get("items", [])
        records: list[SourceRecord] = []
        for specimen in items[: self.max_specimens]:
            collection = specimen.get("collection") or {}
            if self.collection_filter and collection.get("name") != self.collection_filter:
                continue
            label = str(specimen.get("label", "")).strip()
            genotype = specimen.get("genotype") or {}
            lines = [
                f"Specimen: {label}",
                f"Portal specimen id: {specimen.get('id')}",
                f"Collection: {collection.get('name')}",
                f"Neuron (soma) count: {specimen.get('neuronCount')}",
            ]
            if genotype.get("name"):
                lines.append(f"Genotype: {genotype['name']}")
            records.append(
                SourceRecord(
                    record_id=f"morphology_portal::specimen::{specimen.get('id')}",
                    connector=self.name,
                    source_kind=SourceKind.MORPHOLOGY_PORTAL,
                    title=f"Portal specimen {label}",
                    body="\n".join(lines),
                    source_uri=f"nmcp://specimens/{specimen.get('id')}",
                    entity_keys=[label] if label else [],
                    metadata={
                        "specimen_id": specimen.get("id"),
                        "neuron_count": specimen.get("neuronCount"),
                        "collection": collection.get("name"),
                    },
                )
            )
        return records

    def describe(self) -> dict[str, str]:
        return {
            "name": self.name,
            "mode": "read_only",
            "collection_filter": self.collection_filter or "(all)",
            "purpose": "Index morphology portal specimens (label, id, soma count, genotype).",
        }
