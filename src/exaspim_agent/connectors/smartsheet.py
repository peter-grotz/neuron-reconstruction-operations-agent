from __future__ import annotations

from collections import defaultdict
import json
import re
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from exaspim_agent.connectors.base import DataConnector
from exaspim_agent.config import SmartsheetSheetConfig
from exaspim_agent.domain.models import SourceKind, SourceRecord


FIELD_ALIASES = {
    "sample_id": [
        "sample id",
        "sample",
        "specimen id",
        "specimen",
        "mouse id",
        "labtracks",
        "labtracks id",
        "labtracks/specimen id",
        "labtracks specimen id",
    ],
    "project_id": ["project id", "project"],
    "genotype": ["genotype", "driver genotype", "cre line"],
    "status": ["status one", "status 1", "status", "current status", "processing status"],
    "status_one": ["status one", "status 1"],
    "manual_soma_compartment": [
        "neuron manually estimated soma compartment",
        "manual soma compartment",
        "manually estimated soma compartment",
    ],
    "ccf_soma_compartment": [
        "neuron ccf soma compartment",
        "ccf soma compartment",
        "soma ccf compartment",
    ],
    "reporter": ["reporter used", "reporter", "fluorophore", "reporter color", "label"],
    "imaging_notes": ["imaging notes", "imaging note", "notes"],
    "neuroglancer_link": ["neuroglancer link", "neuroglancer", "ng link", "raw ng link"],
    "data_processing_status": ["data processing status", "processing status", "pipeline status"],
    "tissue_processing_status": ["tissue processing status", "tissue status"],
    "registration_status": [
        "manual registration status",
        "registration status",
        "registration stage",
        "registration file creation status",
        "stage",
    ],
}

NEURON_ID_PATTERN = re.compile(r"^(N\d+)-(\d+)$", re.IGNORECASE)


class SmartsheetConnector(DataConnector):
    name = "smartsheet"

    def __init__(
        self,
        api_token: str,
        sheets: list[SmartsheetSheetConfig],
        api_base_url: str = "https://api.smartsheet.com/2.0",
        integration_source: str = "AI,ExASPIM,OperationsAgent",
    ) -> None:
        self.api_token = api_token
        self.sheets = sheets
        self.api_base_url = api_base_url.rstrip("/")
        self.integration_source = integration_source

    def fetch(self) -> list[SourceRecord]:
        sheet_summaries = self._list_sheets()
        records: list[SourceRecord] = []
        for sheet_config in self.sheets:
            summary = self._resolve_sheet_summary(sheet_config, sheet_summaries)
            sheet_payload = self._get_sheet(summary["id"])
            records.extend(self._sheet_to_records(sheet_config, sheet_payload))
        return records

    def describe(self) -> dict[str, str]:
        return {
            "name": self.name,
            "mode": "read_only",
            "sheet_count": str(len(self.sheets)),
            "purpose": (
                "Read operational project tracking rows from approved Smartsheet sheets with preserved "
                "hierarchy and key domain fields."
            ),
        }

    def _list_sheets(self) -> list[dict[str, Any]]:
        payload = self._request_json("sheets", {"includeAll": "true"})
        return payload.get("data", [])

    def _get_sheet(self, sheet_id: str) -> dict[str, Any]:
        return self._request_json(
            "sheets/{sheet_id}".format(sheet_id=sheet_id),
            {"include": "format,rowPermalink,objectValue"},
        )

    def _request_json(self, path: str, params: Optional[dict[str, str]] = None) -> dict[str, Any]:
        url = "{base}/{path}".format(base=self.api_base_url, path=path.lstrip("/"))
        if params:
            url = "{url}?{params}".format(url=url, params=urlencode(params))
        request = Request(
            url,
            headers={
                "Authorization": "Bearer {token}".format(token=self.api_token),
                "Accept": "application/json",
                "User-Agent": self.integration_source,
            },
        )
        try:
            with urlopen(request) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError("Smartsheet API request failed for {url}: {body}".format(url=url, body=body)) from exc
        except URLError as exc:
            raise RuntimeError("Smartsheet API request failed for {url}: {error}".format(url=url, error=exc)) from exc

    def _resolve_sheet_summary(
        self,
        sheet_config: SmartsheetSheetConfig,
        sheet_summaries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        reference = sheet_config.reference.strip()
        if reference.isdigit():
            return {"id": reference, "name": sheet_config.name, "permalink": reference}

        reference_permalink = self._normalized_permalink(reference)
        reference_slug = self._sheet_slug(reference)
        reference_name = _normalize_label(sheet_config.name)

        for summary in sheet_summaries:
            summary_permalink = self._normalized_permalink(str(summary.get("permalink", "")))
            summary_slug = self._sheet_slug(str(summary.get("permalink", "")))
            summary_name = _normalize_label(str(summary.get("name", "")))

            if reference_permalink and summary_permalink and reference_permalink == summary_permalink:
                return summary
            if reference_slug and summary_slug and reference_slug == summary_slug:
                return summary
            if reference_name and summary_name and reference_name == summary_name:
                return summary

        raise RuntimeError(
            "Could not resolve Smartsheet sheet reference `{reference}` for `{name}`.".format(
                reference=sheet_config.reference,
                name=sheet_config.name,
            )
        )

    def _normalized_permalink(self, value: str) -> str:
        if not value:
            return ""
        parsed = urlparse(value.strip())
        if not parsed.scheme or not parsed.netloc:
            return ""
        return "{scheme}://{netloc}{path}".format(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            path=parsed.path.rstrip("/"),
        )

    def _sheet_slug(self, value: str) -> str:
        if not value:
            return ""
        parsed = urlparse(value.strip())
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0].lower() == "sheets":
            return path_parts[1].lower()
        if not parsed.scheme and not parsed.netloc:
            return value.strip().lower()
        return ""

    def _sheet_to_records(
        self,
        sheet_config: SmartsheetSheetConfig,
        sheet_payload: dict[str, Any],
    ) -> list[SourceRecord]:
        columns_by_id = {column["id"]: column for column in sheet_payload.get("columns", [])}
        rows = sheet_payload.get("rows", [])
        rows_by_id = {row["id"]: row for row in rows}
        children_by_parent: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if "parentId" in row:
                children_by_parent[row["parentId"]].append(row)

        records: list[SourceRecord] = []
        for row in rows:
            row_values = self._row_values(row, columns_by_id)
            row_formats = self._row_formats(row, columns_by_id)
            parent_row = rows_by_id.get(row.get("parentId"))
            parent_values = self._row_values(parent_row, columns_by_id) if parent_row else {}
            key_fields = self._extract_key_fields(sheet_config, row_values, parent_values)
            record_id = "{sheet_key}:{row_id}".format(sheet_key=sheet_config.key, row_id=row["id"])
            source_uri = row.get("permalink") or "smartsheet://sheet/{sheet_id}/row/{row_id}".format(
                sheet_id=sheet_payload.get("id"),
                row_id=row["id"],
            )
            records.append(
                SourceRecord(
                    record_id=record_id,
                    connector=self.name,
                    source_kind=SourceKind.SMARTSHEET,
                    title=self._record_title(sheet_config, row, row_values, parent_values, key_fields),
                    body=self._record_body(
                        sheet_config=sheet_config,
                        sheet_payload=sheet_payload,
                        row=row,
                        row_values=row_values,
                        parent_values=parent_values,
                        key_fields=key_fields,
                        child_count=len(children_by_parent.get(row["id"], [])),
                    ),
                    source_uri=source_uri,
                    entity_keys=self._entity_keys(key_fields, row_values, parent_values),
                    metadata={
                        "sheet_key": sheet_config.key,
                        "sheet_name": sheet_payload.get("name", sheet_config.name),
                        "sheet_reference": sheet_config.reference,
                        "sheet_id": str(sheet_payload.get("id")),
                        "row_id": str(row["id"]),
                        "row_number": row.get("rowNumber"),
                        "parent_row_id": str(row.get("parentId")) if row.get("parentId") is not None else None,
                        "is_child_row": row.get("parentId") is not None,
                        "child_row_count": len(children_by_parent.get(row["id"], [])),
                        "key_fields": key_fields,
                        "important_values": self._important_values(sheet_config, row_values, parent_values),
                        "columns": row_values,
                        "parent_columns": parent_values,
                        "format_columns": row_formats,
                        **key_fields,
                    },
                )
            )
        return records

    def _row_values(self, row: Optional[dict[str, Any]], columns_by_id: dict[Any, dict[str, Any]]) -> dict[str, str]:
        if not row:
            return {}

        values: dict[str, str] = {}
        for cell in row.get("cells", []):
            column = columns_by_id.get(cell.get("columnId"), {})
            title = str(column.get("title") or cell.get("columnId"))
            display = cell.get("displayValue")
            raw_value = cell.get("value")
            object_value = cell.get("objectValue")
            if display not in (None, ""):
                value = str(display)
            elif raw_value not in (None, ""):
                value = str(raw_value)
            elif object_value not in (None, ""):
                value = json.dumps(object_value, sort_keys=True)
            else:
                value = ""
            values[title] = value
        return {key: value for key, value in values.items() if value not in ("", "None")}

    def _row_formats(self, row: Optional[dict[str, Any]], columns_by_id: dict[Any, dict[str, Any]]) -> dict[str, str]:
        if not row:
            return {}
        formats: dict[str, str] = {}
        for cell in row.get("cells", []):
            if not cell.get("format"):
                continue
            column = columns_by_id.get(cell.get("columnId"), {})
            title = str(column.get("title") or cell.get("columnId"))
            formats[title] = str(cell["format"])
        return formats

    def _extract_key_fields(
        self,
        sheet_config: SmartsheetSheetConfig,
        row_values: dict[str, str],
        parent_values: dict[str, str],
    ) -> dict[str, str]:
        combined = dict(parent_values)
        combined.update(row_values)
        extracted: dict[str, str] = {}
        for field_name, aliases in FIELD_ALIASES.items():
            matched = _find_value(combined, aliases)
            if matched:
                extracted[field_name] = matched
        if sheet_config.key == "neuron_reconstruction" and "genotype" in extracted:
            extracted["reconstruction_sheet_genotype"] = extracted.pop("genotype")
        self._derive_neuron_and_sample_ids(extracted, combined)
        return extracted

    def _derive_neuron_and_sample_ids(
        self,
        extracted: dict[str, str],
        combined: dict[str, str],
    ) -> None:
        id_candidates = [
            _find_value(combined, ["id"]),
            _find_value(combined, ["hust id"]),
            extracted.get("sample_id"),
        ]
        for candidate in id_candidates:
            if not candidate:
                continue
            matched = NEURON_ID_PATTERN.match(candidate.strip())
            if not matched:
                continue
            neuron_id, sample_id = matched.groups()
            extracted["neuron_id"] = candidate.strip()
            extracted["sample_id"] = sample_id
            extracted["sample_id_source"] = "derived_from_neuron_id"
            return

    def _important_values(
        self,
        sheet_config: SmartsheetSheetConfig,
        row_values: dict[str, str],
        parent_values: dict[str, str],
    ) -> dict[str, str]:
        combined = dict(parent_values)
        combined.update(row_values)
        selected: dict[str, str] = {}
        for label in sheet_config.important_columns:
            matched = _find_value(combined, [label])
            if matched:
                selected[label] = matched
        return selected

    def _entity_keys(
        self,
        key_fields: dict[str, str],
        row_values: dict[str, str],
        parent_values: dict[str, str],
    ) -> list[str]:
        ordered_values = [
            key_fields.get("sample_id"),
            key_fields.get("project_id"),
            key_fields.get("genotype"),
            key_fields.get("manual_soma_compartment"),
            key_fields.get("ccf_soma_compartment"),
            key_fields.get("status_one"),
            key_fields.get("registration_status"),
        ]
        combined = list(row_values.values()) + list(parent_values.values())
        keys: list[str] = []
        for value in ordered_values + combined:
            if not value:
                continue
            if len(value) > 120:
                continue
            if value not in keys:
                keys.append(value)
        return keys[:25]

    def _record_title(
        self,
        sheet_config: SmartsheetSheetConfig,
        row: dict[str, Any],
        row_values: dict[str, str],
        parent_values: dict[str, str],
        key_fields: dict[str, str],
    ) -> str:
        sample = key_fields.get("sample_id")
        genotype = key_fields.get("genotype")
        status = key_fields.get("status_one") or key_fields.get("status") or key_fields.get("registration_status")
        manual = key_fields.get("manual_soma_compartment")
        ccf = key_fields.get("ccf_soma_compartment")
        segments = [sheet_config.name]
        if sample:
            segments.append(sample)
        if manual or ccf:
            soma_parts = [part for part in [manual, ccf] if part]
            segments.append("/".join(soma_parts))
        if status:
            segments.append(status)
        elif genotype:
            segments.append(genotype)
        if row.get("parentId") is not None and parent_values:
            segments.append("child row")
        return " | ".join(segments)

    def _record_body(
        self,
        sheet_config: SmartsheetSheetConfig,
        sheet_payload: dict[str, Any],
        row: dict[str, Any],
        row_values: dict[str, str],
        parent_values: dict[str, str],
        key_fields: dict[str, str],
        child_count: int,
    ) -> str:
        lines = [
            "Sheet: {name} ({key})".format(name=sheet_payload.get("name", sheet_config.name), key=sheet_config.key),
            "Sheet description: {description}".format(description=sheet_config.description or "n/a"),
            "Row ID: {row_id}".format(row_id=row["id"]),
            "Hierarchy: {hierarchy}".format(
                hierarchy="child row of {parent_id}".format(parent_id=row.get("parentId"))
                if row.get("parentId") is not None
                else "top-level row"
            ),
        ]
        if child_count:
            lines.append("Child rows: {count}".format(count=child_count))
        if key_fields:
            lines.append("Key fields:")
            for key, value in key_fields.items():
                lines.append("- {key}: {value}".format(key=key, value=value))
        important_values = self._important_values(sheet_config, row_values, parent_values)
        if important_values:
            lines.append("Important columns:")
            for key, value in important_values.items():
                lines.append("- {key}: {value}".format(key=key, value=value))
        if parent_values:
            lines.append("Parent row context:")
            for key, value in parent_values.items():
                lines.append("- {key}: {value}".format(key=key, value=value))
        if row_values:
            lines.append("Row values:")
            for key, value in row_values.items():
                lines.append("- {key}: {value}".format(key=key, value=value))
        return "\n".join(lines)


def _normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _find_value(values: dict[str, str], aliases: list[str]) -> Optional[str]:
    normalized_values = {_normalize_label(key): value for key, value in values.items()}
    normalized_aliases = [_normalize_label(alias) for alias in aliases]

    for alias in normalized_aliases:
        if alias in normalized_values and normalized_values[alias]:
            return normalized_values[alias]

    for alias in normalized_aliases:
        alias_token_count = len(alias.split())
        if alias_token_count < 2:
            continue
        for key, value in normalized_values.items():
            if (
                key == alias
                or key.startswith(alias + " ")
                or key.endswith(" " + alias)
                or (" " + alias + " ") in (" " + key + " ")
            ):
                if value:
                    return value
    return None
