"""Tool result models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from gstarcad_mcp.schemas.common import StrictModel
from gstarcad_mcp.schemas.entities import EntityRef


class GcadStatusResult(StrictModel):
    server_version: str
    runtime_id: UUID
    protocol_sdk_version: str
    platform: str
    permission_profile: str
    runtime_state: str
    queue_depth: int = Field(ge=0)
    gstarcad_installed: bool | None = None
    com_registered: bool | None = None
    connected: bool = False
    connected_prog_id: str | None = None
    connection_mode: str | None = None
    application_responsive: bool | None = None
    active_document_id: UUID | None = None
    document_count: int = Field(default=0, ge=0)
    screenshot_available: bool = False
    transaction_modes: list[str] = Field(default_factory=list)
    external_change_detection: str = "not_available"
    startup_error: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ErrorInfo(StrictModel):
    code: str
    message: str
    retryable: bool = False
    action_index: int | None = None


class ActionResult(StrictModel):
    index: int = Field(ge=0)
    action_id: str | None = None
    op: str
    status: Literal["succeeded", "failed", "skipped", "rolled_back"]
    entities: list[EntityRef] = Field(default_factory=list)
    handles: list[str] = Field(default_factory=list)
    artifact_uris: list[str] = Field(default_factory=list)
    error: ErrorInfo | None = None
    duration_ms: int = Field(default=0, ge=0)


class BatchOperationResult(StrictModel):
    status: Literal["succeeded", "partial"]
    operation_id: UUID
    document_id: UUID
    revision_before: int = Field(ge=0)
    revision_after: int = Field(ge=0)
    transaction_mode: Literal[
        "undo_group",
        "copy_on_write",
        "compensating_actions",
        "best_effort",
    ] = "best_effort"
    rollback_status: Literal[
        "not_needed",
        "succeeded",
        "partial",
        "not_available",
    ] = "not_needed"
    actions: list[ActionResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duration_ms: int = Field(default=0, ge=0)


class SnapshotResult(StrictModel):
    document_id: UUID
    revision: int = Field(ge=0)
    resource_uri: str
    relative_path: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    mime_type: Literal["image/png"] = "image/png"
    byte_size: int = Field(ge=0)
    sha256: str | None = None
    uniform: bool = False
    captured_at: datetime
