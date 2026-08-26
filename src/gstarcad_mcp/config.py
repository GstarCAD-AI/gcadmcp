"""Server configuration: safe defaults < TOML file < environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import tomllib
from pydantic import BaseModel, ConfigDict, Field

PermissionProfile = Literal["readonly", "assistive", "authoring", "automation"]

_ENV_PREFIX = "GSTARCAD_MCP_"


class StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServerSection(StrictConfig):
    name: str = "gstarcad-mcp"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    permission_profile: PermissionProfile = "authoring"


class CadSection(StrictConfig):
    prog_id: str = "auto"
    create_if_missing: bool = True
    visible: bool = True
    startup_wait_seconds: float = Field(default=20.0, ge=0)
    shutdown_timeout_seconds: float = Field(default=10.0, gt=0)
    max_queue_depth: int = Field(default=128, ge=1)
    reconnect_attempts: int = Field(default=0, ge=0)
    quit_launched_instance_on_exit: bool = False
    operation_warning_seconds: float = Field(default=30.0, gt=0)


class WorkspaceSection(StrictConfig):
    root: str = ""
    allow_unc: bool = False
    allow_absolute_paths: bool = False
    allow_overwrite: bool = False


class LimitsSection(StrictConfig):
    max_actions_per_batch: int = Field(default=500, ge=1)
    max_total_vertices_per_batch: int = Field(default=100_000, ge=1)
    max_vertices_per_polyline: int = Field(default=10_000, ge=2)
    max_query_page_size: int = Field(default=1000, ge=1)
    max_entity_handles_per_request: int = Field(default=1000, ge=1)
    max_text_length: int = Field(default=20_000, ge=1)
    max_table_rows: int = Field(default=200, ge=1)
    max_table_columns: int = Field(default=100, ge=1)
    max_table_cells: int = Field(default=10_000, ge=1)
    max_screenshot_width: int = Field(default=4096, ge=320)
    max_screenshot_height: int = Field(default=4096, ge=240)
    max_resource_bytes: int = Field(default=67_108_864, ge=1)
    max_run_artifacts_bytes: int = Field(default=268_435_456, ge=1)
    max_queue_depth: int = Field(default=128, ge=1)


class EvidenceSection(StrictConfig):
    require_screenshot_for_success: bool = True
    capture_bounds_by_default: bool = False
    hash_artifacts: bool = True


class IdempotencySection(StrictConfig):
    retention_days: int = Field(default=30, ge=1)
    max_records: int = Field(default=100_000, ge=1)


class LoggingSection(StrictConfig):
    file_enabled: bool = True
    max_file_bytes: int = Field(default=10_485_760, ge=1024)
    backup_count: int = Field(default=5, ge=0)


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server: ServerSection = Field(default_factory=ServerSection)
    cad: CadSection = Field(default_factory=CadSection)
    workspace: WorkspaceSection = Field(default_factory=WorkspaceSection)
    limits: LimitsSection = Field(default_factory=LimitsSection)
    evidence: EvidenceSection = Field(default_factory=EvidenceSection)
    idempotency: IdempotencySection = Field(default_factory=IdempotencySection)
    logging: LoggingSection = Field(default_factory=LoggingSection)

    def workspace_root(self) -> Path:
        raw = self.workspace.root or str(
            Path(os.environ.get("USERPROFILE", Path.home())) / "Documents" / "GstarCAD-MCP"
        )
        return Path(os.path.expandvars(raw)).resolve()


_SECTION_ENV = {
    "GSTARCAD_MCP_LOG_LEVEL": ("server", "log_level"),
    "GSTARCAD_MCP_PERMISSION_PROFILE": ("server", "permission_profile"),
    "GSTARCAD_MCP_WORKSPACE_ROOT": ("workspace", "root"),
    "GSTARCAD_MCP_PROG_ID": ("cad", "prog_id"),
    "GSTARCAD_MCP_VISIBLE": ("cad", "visible"),
}


def _coerce(value: str, current):
    if isinstance(current, bool):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(current, int) and not isinstance(current, bool):
        return int(value)
    if isinstance(current, float):
        return float(value)
    return value


def load_config(path: str | Path | None = None) -> ServerConfig:
    config_path = path or os.environ.get(_ENV_PREFIX + "CONFIG")
    data: dict = {}
    if config_path:
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
    config = ServerConfig.model_validate(data)
    for env_name, (section, field) in _SECTION_ENV.items():
        value = os.environ.get(env_name)
        if value is None:
            continue
        section_obj = getattr(config, section)
        setattr(section_obj, field, _coerce(value, getattr(section_obj, field)))
    return config
