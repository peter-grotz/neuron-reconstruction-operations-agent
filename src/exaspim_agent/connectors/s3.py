from __future__ import annotations

import json
from typing import Any

from exaspim_agent.connectors.base import DataConnector
from exaspim_agent.domain.models import SourceKind, SourceRecord


class S3Connector(DataConnector):
    name = "s3"

    def __init__(
        self,
        bucket: str,
        prefixes: list[str],
        region: str,
        max_objects_per_prefix: int = 25,
    ) -> None:
        self.bucket = bucket
        self.prefixes = prefixes
        self.region = region
        self.max_objects_per_prefix = max_objects_per_prefix

    def fetch(self) -> list[SourceRecord]:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required for S3 ingestion. Install with `.[aws]`.") from exc

        client = boto3.client("s3", region_name=self.region)
        records: list[SourceRecord] = []
        for prefix in self.prefixes:
            listed = client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
                MaxKeys=self.max_objects_per_prefix,
            )
            for item in listed.get("Contents", []):
                key = item["Key"]
                body = self._read_text_body(client, key)
                records.append(
                    SourceRecord(
                        record_id=key,
                        connector=self.name,
                        source_kind=SourceKind.S3,
                        title=key.split("/")[-1] or key,
                        body=body,
                        source_uri=f"s3://{self.bucket}/{key}",
                        metadata={
                            "bucket": self.bucket,
                            "key": key,
                            "size_bytes": item.get("Size"),
                            "last_modified": item.get("LastModified").isoformat()
                            if item.get("LastModified")
                            else None,
                        },
                    )
                )
        return records

    def describe(self) -> dict[str, str]:
        return {
            "name": self.name,
            "mode": "read_only",
            "bucket": self.bucket,
            "prefix_count": str(len(self.prefixes)),
            "purpose": "Read text-like pipeline manifests, metadata, and logs from S3.",
        }

    def _read_text_body(self, client: Any, key: str) -> str:
        if not key.endswith((".txt", ".json", ".csv", ".log", ".md")):
            return f"Binary or unsupported object at s3://{self.bucket}/{key}"

        payload = client.get_object(Bucket=self.bucket, Key=key)["Body"].read().decode("utf-8", errors="replace")
        if key.endswith(".json"):
            try:
                parsed = json.loads(payload)
                return json.dumps(parsed, indent=2, sort_keys=True)
            except json.JSONDecodeError:
                return payload
        return payload
