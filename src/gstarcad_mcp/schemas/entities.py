"""Entity summary models returned across the MCP boundary."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from gstarcad_mcp.schemas.common import Bounds3, StrictModel


class EntityRef(StrictModel):
    document_id: UUID | None = None
    handle: str = Field(min_length=1, max_length=64)
    entity_type: str = Field(default="", max_length=128)
    layer: str | None = Field(default=None, max_length=255)
    color: int | None = None
    linetype: str | None = Field(default=None, max_length=128)
    lineweight: int | None = None
    closed: bool | None = None
    text: str | None = Field(default=None, max_length=20_000)
    bounds: Bounds3 | None = None
