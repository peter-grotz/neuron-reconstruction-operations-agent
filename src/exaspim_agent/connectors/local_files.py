from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from exaspim_agent.connectors.base import DataConnector
from exaspim_agent.domain.models import SourceKind, SourceRecord


class LocalJsonConnector(DataConnector):
    name = "local_json"

    def __init__(self, path: Path) -> None:
        self.path = path

    def fetch(self) -> list[SourceRecord]:
        if not self.path.exists():
            return []

        raw_payload = json.loads(self.path.read_text())
        raw_records = raw_payload["records"] if isinstance(raw_payload, dict) else raw_payload
        records: list[SourceRecord] = []
        for item in raw_records:
            metadata = item.get("metadata", {})
            records.append(
                SourceRecord(
                    record_id=str(item["record_id"]),
                    connector=item.get("connector", self.name),
                    source_kind=SourceKind(item.get("source_kind", SourceKind.LOCAL_JSON)),
                    title=item.get("title") or f"Record {item['record_id']}",
                    body=item.get("body") or item.get("text") or item.get("content", ""),
                    source_uri=item.get("source_uri", f"local://{item['record_id']}"),
                    entity_keys=[str(key) for key in item.get("entity_keys", [])],
                    metadata=self._stringify_non_scalars(metadata),
                )
            )
        return records

    def describe(self) -> dict[str, str]:
        return {
            "name": self.name,
            "mode": "read_only",
            "path": str(self.path),
            "purpose": "Load local export files or mock datasets into the canonical knowledge base.",
        }

    @staticmethod
    def _stringify_non_scalars(value: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(item, (str, int, float, bool)) or item is None:
                result[key] = item
            else:
                result[key] = json.dumps(item, sort_keys=True)
        return result
