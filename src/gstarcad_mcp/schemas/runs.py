"""Run/evidence models (guideline 20)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import Field

from gstarcad_mcp.schemas.common import StrictModel


class RunStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CONFLICTED = "conflicted"


class ValidationCheck(StrictModel):
    check_id: str = Field(max_length=128)
    category: str = Field(max_length=64)
    status: Literal["passed", "failed", "warning", "not_run"]
    message: str = Field(max_length=2000)
    evidence_uris: list[str] = Field(default_factory=list)


class RepairRecord(StrictModel):
    repair_id: str = Field(max_length=128)
    cause: str = Field(max_length=2000)
    action: str = Field(max_length=2000)
    outcome: str = Field(max_length=2000)
    timestamp: datetime


class RunManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: UUID
    runtime_id: UUID
    status: RunStatus = RunStatus.PLANNED
    title: str = Field(max_length=500)
    intent: str = Field(max_length=20_000)
    units: str = Field(default="mm", max_length=32)
    assumptions: list[str] = Field(default_factory=list)
    document_id: UUID | None = None
    document_revision_before: int | None = None
    document_revision_after: int | None = None
    created_at: datetime
    updated_at: datetime
    artifacts: dict[str, str] = Field(default_factory=dict)
    validations: list[ValidationCheck] = Field(default_factory=list)
    repairs: list[RepairRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    last_operation_id: UUID | None = None
