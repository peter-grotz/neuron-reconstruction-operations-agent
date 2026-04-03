from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


class SmartsheetSheetConfig(BaseModel):
    key: str
    name: str
    reference: str
    description: Optional[str] = None
    important_columns: list[str] = Field(default_factory=list)


class TeamsChannelConfig(BaseModel):
    key: str
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    description: Optional[str] = None
    include_replies: bool = True


class Settings(BaseModel):
    app_name: str = "ExA-SPIM Operations Agent"
    environment: str = "dev"
    local_json_path: Path = Path("data/sample/local_records.json")
    export_dir: Path = Path("exports")
    sqlite_path: Path = Path("exports/exaspim_agent.db")
    retrieval_top_k: int = 6
    chunk_size: int = 900
    chunk_overlap: int = 120

    smartsheet_api_token: Optional[str] = None
    smartsheet_token_file: Optional[Path] = Path("CO_API/CO_ACCESS_TOKEN.txt")
    smartsheet_api_base_url: str = "https://api.smartsheet.com/2.0"
    smartsheet_integration_source: str = "AI,ExASPIM,OperationsAgent"
    smartsheet_sheet_ids: list[str] = Field(default_factory=list)
    smartsheet_sheets: list[SmartsheetSheetConfig] = Field(default_factory=lambda: _default_smartsheet_sheets())

    teams_tenant_id: Optional[str] = None
    teams_client_id: Optional[str] = None
    teams_client_secret: Optional[str] = None
    teams_token_file: Optional[Path] = None
    teams_graph_base_url: str = "https://graph.microsoft.com/v1.0"
    teams_authority_url: str = "https://login.microsoftonline.com"
    teams_scope: str = "https://graph.microsoft.com/.default"
    teams_max_messages_per_channel: int = 100
    teams_channels: list[TeamsChannelConfig] = Field(default_factory=list)

    aws_region: str = "us-west-2"
    s3_bucket: Optional[str] = None
    s3_prefixes: list[str] = Field(default_factory=list)
    s3_max_objects_per_prefix: int = 25

    openai_api_key: Optional[str] = None

    @classmethod
    def from_env(cls, env_file: str = ".env") -> "Settings":
        env_map = _load_env_file(env_file)
        values = {
            "environment": _env_value("EXASPIM_ENVIRONMENT", env_map, "dev"),
            "local_json_path": Path(_env_value("EXASPIM_LOCAL_JSON_PATH", env_map, "data/sample/local_records.json")),
            "export_dir": Path(_env_value("EXASPIM_EXPORT_DIR", env_map, "exports")),
            "sqlite_path": Path(_env_value("EXASPIM_SQLITE_PATH", env_map, "exports/exaspim_agent.db")),
            "retrieval_top_k": int(_env_value("EXASPIM_RETRIEVAL_TOP_K", env_map, 6)),
            "chunk_size": int(_env_value("EXASPIM_CHUNK_SIZE", env_map, 900)),
            "chunk_overlap": int(_env_value("EXASPIM_CHUNK_OVERLAP", env_map, 120)),
            "smartsheet_api_token": _optional_env_value("EXASPIM_SMARTSHEET_API_TOKEN", env_map),
            "smartsheet_token_file": _optional_path_env_value(
                "EXASPIM_SMARTSHEET_TOKEN_FILE",
                env_map,
                Path("CO_API/CO_ACCESS_TOKEN.txt"),
            ),
            "smartsheet_api_base_url": _env_value(
                "EXASPIM_SMARTSHEET_API_BASE_URL",
                env_map,
                "https://api.smartsheet.com/2.0",
            ),
            "smartsheet_integration_source": _env_value(
                "EXASPIM_SMARTSHEET_INTEGRATION_SOURCE",
                env_map,
                "AI,ExASPIM,OperationsAgent",
            ),
            "smartsheet_sheet_ids": _load_list_env("EXASPIM_SMARTSHEET_SHEET_IDS", env_map),
            "smartsheet_sheets": _load_smartsheet_sheets_env(
                "EXASPIM_SMARTSHEET_SHEETS",
                env_map,
                _default_smartsheet_sheets(),
            ),
            "teams_tenant_id": _optional_env_value("EXASPIM_TEAMS_TENANT_ID", env_map),
            "teams_client_id": _optional_env_value("EXASPIM_TEAMS_CLIENT_ID", env_map),
            "teams_client_secret": _optional_env_value("EXASPIM_TEAMS_CLIENT_SECRET", env_map),
            "teams_token_file": _optional_path_env_value("EXASPIM_TEAMS_TOKEN_FILE", env_map, None),
            "teams_graph_base_url": _env_value(
                "EXASPIM_TEAMS_GRAPH_BASE_URL",
                env_map,
                "https://graph.microsoft.com/v1.0",
            ),
            "teams_authority_url": _env_value(
                "EXASPIM_TEAMS_AUTHORITY_URL",
                env_map,
                "https://login.microsoftonline.com",
            ),
            "teams_scope": _env_value(
                "EXASPIM_TEAMS_SCOPE",
                env_map,
                "https://graph.microsoft.com/.default",
            ),
            "teams_max_messages_per_channel": int(
                _env_value("EXASPIM_TEAMS_MAX_MESSAGES_PER_CHANNEL", env_map, 100)
            ),
            "teams_channels": _load_teams_channels_env("EXASPIM_TEAMS_CHANNELS", env_map),
            "aws_region": _env_value("EXASPIM_AWS_REGION", env_map, "us-west-2"),
            "s3_bucket": _optional_env_value("EXASPIM_S3_BUCKET", env_map),
            "s3_prefixes": _load_list_env("EXASPIM_S3_PREFIXES", env_map),
            "s3_max_objects_per_prefix": int(_env_value("EXASPIM_S3_MAX_OBJECTS_PER_PREFIX", env_map, 25)),
            "openai_api_key": _optional_env_value("EXASPIM_OPENAI_API_KEY", env_map),
        }
        return cls(**values)

    def resolve_smartsheet_token(self) -> Optional[str]:
        if self.smartsheet_api_token:
            return self.smartsheet_api_token.strip() or None
        if self.smartsheet_token_file and self.smartsheet_token_file.exists():
            token = self.smartsheet_token_file.read_text().strip()
            return token or None
        return None

    def effective_smartsheet_sheets(self) -> list[SmartsheetSheetConfig]:
        if self.smartsheet_sheets:
            return self.smartsheet_sheets
        return [
            SmartsheetSheetConfig(
                key=f"smartsheet_sheet_{index + 1}",
                name=f"Smartsheet Sheet {index + 1}",
                reference=sheet_id,
            )
            for index, sheet_id in enumerate(self.smartsheet_sheet_ids)
        ]

    def resolve_teams_client_secret(self) -> Optional[str]:
        if self.teams_client_secret:
            return self.teams_client_secret.strip() or None
        if self.teams_token_file and self.teams_token_file.exists():
            token = self.teams_token_file.read_text().strip()
            return token or None
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings.from_env()
    settings.export_dir.mkdir(parents=True, exist_ok=True)
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return settings


def _load_env_file(env_file: str) -> dict[str, str]:
    path = Path(env_file)
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _env_value(key: str, env_map: dict[str, str], default: Any) -> Any:
    return os.environ.get(key, env_map.get(key, default))


def _optional_env_value(key: str, env_map: dict[str, str]) -> Optional[str]:
    value = _env_value(key, env_map, None)
    if value in ("", None):
        return None
    return str(value)


def _optional_path_env_value(key: str, env_map: dict[str, str], default: Optional[Path]) -> Optional[Path]:
    value = _env_value(key, env_map, default)
    if value in ("", None):
        return None
    return Path(str(value))


def _load_list_env(key: str, env_map: dict[str, str]) -> list[str]:
    value = _env_value(key, env_map, "[]")
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except json.JSONDecodeError:
        pass
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _load_smartsheet_sheets_env(
    key: str,
    env_map: dict[str, str],
    default: list[SmartsheetSheetConfig],
) -> list[SmartsheetSheetConfig]:
    value = _env_value(key, env_map, None)
    if value in (None, ""):
        return default

    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{key} must be a JSON array of sheet config objects.") from exc

    if not isinstance(parsed, list):
        raise ValueError(f"{key} must be a JSON array of sheet config objects.")

    return [SmartsheetSheetConfig(**item) for item in parsed]


def _load_teams_channels_env(key: str, env_map: dict[str, str]) -> list[TeamsChannelConfig]:
    value = _env_value(key, env_map, None)
    if value in (None, ""):
        return []

    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{key} must be a JSON array of Teams channel config objects.") from exc

    if not isinstance(parsed, list):
        raise ValueError(f"{key} must be a JSON array of Teams channel config objects.")

    return [TeamsChannelConfig(**item) for item in parsed]


def _default_smartsheet_sheets() -> list[SmartsheetSheetConfig]:
    return [
        SmartsheetSheetConfig(
            key="neuron_reconstruction",
            name="Neuron Reconstruction",
            reference="https://app.smartsheet.com/sheets/pJCcRc8WGjj2hhfWgFQQxhXmj4cj4gCCmvJh3hH1?view=grid",
            description=(
                "Neuron-level reconstruction tracking with parent rows for specimen context and child rows "
                "for reconstructed cells."
            ),
            important_columns=[
                "Mouse ID",
                "ID",
                "Genotype",
                "Manual Estimated Soma Compartment",
                "CCF Soma Compartment",
                "Status 1",
            ],
        ),
        SmartsheetSheetConfig(
            key="specimen_pipeline",
            name="Specimen Pipeline Overview",
            reference="https://app.smartsheet.com/sheets/WRGWvgwq83X25p4Xr9PCC47HM7C88RH5cgqRmgx1?view=board",
            description=(
                "Specimen-level tracking for imaging, tissue processing, data processing, genotype, notes, "
                "and neuroglancer links."
            ),
            important_columns=[
                "Sample",
                "Genotype",
                "Imaging Notes",
                "Label",
                "Processing Status",
                "Raw NG Link",
            ],
        ),
        SmartsheetSheetConfig(
            key="manual_registration",
            name="Manual Registration Status",
            reference="https://app.smartsheet.com/sheets/HRFFHXxHP2gfM2CCWmVxvP5PPRjwJ44R2jmRWQv1?view=grid",
            description="Specimen-level manual registration progress and current stage.",
            important_columns=[
                "Specimen ID",
                "Registration Status",
                "Sample ID",
                "Manual Registration Status",
                "Registration File Creation Status",
                "Stage",
            ],
        ),
    ]
