from __future__ import annotations

import base64
import json
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from exaspim_agent.config import CodeOceanCapsuleConfig
from exaspim_agent.connectors.base import DataConnector
from exaspim_agent.domain.models import SourceKind, SourceRecord


class CodeOceanClient:
    """Thin read/write client for the Code Ocean v1 API.

    Auth is HTTP Basic with the API token as the username and an empty password
    (the trailing colon in ``token:``). This is not interchangeable with the git
    credentials the deployment uses for capsule clones — those want the user's
    email as the username instead.
    """

    def __init__(self, token: str, base_url: str, timeout: int = 60) -> None:
        self._auth = "Basic " + base64.b64encode(f"{token}:".encode()).decode()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, body: Optional[dict[str, Any]] = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": self._auth, "User-Agent": "exaspim-ops-agent"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        with urlopen(req, timeout=self.timeout) as response:
            payload = response.read().decode("utf-8", errors="replace")
        return json.loads(payload) if payload else None

    def get_capsule(self, capsule_id: str) -> dict[str, Any]:
        return self._request("GET", f"/capsules/{capsule_id}")

    def list_computations(self, capsule_id: str) -> list[dict[str, Any]]:
        result = self._request("GET", f"/capsules/{capsule_id}/computations")
        return result if isinstance(result, list) else []

    def get_computation(self, computation_id: str) -> dict[str, Any]:
        return self._request("GET", f"/computations/{computation_id}")

    def list_results(self, computation_id: str, path: str = "") -> dict[str, Any]:
        # Note: listing results is a POST with a body, not a GET.
        return self._request("POST", f"/computations/{computation_id}/results", {"path": path})

    def launch_computation(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/computations", body)


def classify_run(computation: dict[str, Any]) -> str:
    """Reduce the three status fields to a single honest verdict.

    ``state`` only reaches ``completed`` — it never reports failure — so success
    cannot be read from it alone. A terminated machine has been observed to
    report ``completed`` / ``exit_code 0`` / ``succeeded`` while syncing nothing,
    so ``has_results == false`` is treated as failure regardless of the rest.
    """
    state = computation.get("state")
    if state != "completed":
        return state or "unknown"
    if computation.get("end_status") == "stopped":
        return "stopped"
    if computation.get("exit_code") not in (0, None) or computation.get("end_status") == "failed":
        return "failed"
    if computation.get("has_results") is False:
        return "failed_no_results"
    return "succeeded"


class CodeOceanConnector(DataConnector):
    """Read-only ingestion of capsule and recent-computation metadata.

    Indexes what each configured capsule is and how its recent runs turned out,
    so the agent can answer "did the last <capsule> run succeed" without a live
    call. It does not launch anything — that is the run tool's job.
    """

    name = "code_ocean"

    def __init__(
        self,
        client: CodeOceanClient,
        capsules: list[CodeOceanCapsuleConfig],
        max_computations: int = 10,
    ) -> None:
        self.client = client
        self.capsules = capsules
        self.max_computations = max_computations

    def fetch(self) -> list[SourceRecord]:
        records: list[SourceRecord] = []
        for capsule in self.capsules:
            records.extend(self._fetch_capsule(capsule))
        return records

    def _fetch_capsule(self, capsule: CodeOceanCapsuleConfig) -> list[SourceRecord]:
        records: list[SourceRecord] = []
        entity_keys = [capsule.key, capsule.capsule_id]

        try:
            meta = self.client.get_capsule(capsule.capsule_id)
        except (HTTPError, URLError, ValueError) as exc:
            meta = {"error": str(exc)}

        body_lines = [
            f"Capsule: {capsule.name} ({capsule.key})",
            f"Capsule ID: {capsule.capsule_id}",
        ]
        if capsule.description:
            body_lines.append(f"Purpose: {capsule.description}")
        for field in ("name", "description", "owner", "slug", "status"):
            if meta.get(field):
                body_lines.append(f"{field}: {meta[field]}")
        records.append(
            SourceRecord(
                record_id=f"code_ocean::capsule::{capsule.capsule_id}",
                connector=self.name,
                source_kind=SourceKind.CODE_OCEAN,
                title=f"Code Ocean capsule: {capsule.name}",
                body="\n".join(body_lines),
                source_uri=f"codeocean://capsules/{capsule.capsule_id}",
                entity_keys=entity_keys,
                metadata={"capsule_id": capsule.capsule_id, "kind": "capsule"},
            )
        )

        try:
            computations = self.client.list_computations(capsule.capsule_id)
        except (HTTPError, URLError, ValueError) as exc:
            computations = []
            body_lines.append(f"(could not list computations: {exc})")

        computations = sorted(
            computations, key=lambda c: c.get("created", 0), reverse=True
        )[: self.max_computations]

        for comp in computations:
            verdict = classify_run(comp)
            lines = [
                f"Computation: {comp.get('name', comp.get('id'))}",
                f"Capsule: {capsule.name} ({capsule.key})",
                f"Verdict: {verdict}",
                f"state={comp.get('state')} end_status={comp.get('end_status')} "
                f"exit_code={comp.get('exit_code')} has_results={comp.get('has_results')}",
                f"run_time_s={comp.get('run_time')}",
            ]
            if comp.get("parameters"):
                lines.append(f"parameters: {comp['parameters']}")
            records.append(
                SourceRecord(
                    record_id=f"code_ocean::computation::{comp.get('id')}",
                    connector=self.name,
                    source_kind=SourceKind.CODE_OCEAN,
                    title=f"CO run {comp.get('name', comp.get('id'))} — {verdict}",
                    body="\n".join(lines),
                    source_uri=f"codeocean://computations/{comp.get('id')}",
                    entity_keys=entity_keys,
                    metadata={
                        "capsule_id": capsule.capsule_id,
                        "computation_id": comp.get("id"),
                        "verdict": verdict,
                        "kind": "computation",
                    },
                )
            )
        return records

    def describe(self) -> dict[str, str]:
        return {
            "name": self.name,
            "mode": "read_only",
            "capsule_count": str(len(self.capsules)),
            "purpose": "Index Code Ocean capsule metadata and recent computation outcomes.",
        }
