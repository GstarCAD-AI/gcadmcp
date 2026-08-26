"""Document identity models."""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import Field

from gstarcad_mcp.schemas.common import StrictModel


class DocumentOwnership(str, Enum):
    EXTERNAL = "external"
    SERVER = "server"


class DocumentRef(StrictModel):
    document_id: UUID
    name: str
    relative_path: str | None = None
    ownership: DocumentOwnership
    read_only: bool = False
    active: bool = False
    revision: int = Field(default=0, ge=0)
    dirty: bool | None = None


class DocumentOperationResult(StrictModel):
    runtime_id: UUID
    document: DocumentRef
    operation_id: UUID | None = None
    warnings: list[str] = Field(default_factory=list)
