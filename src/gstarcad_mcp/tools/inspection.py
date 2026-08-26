"""Read-only inspection tools (§16.8-16.11)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from gstarcad_mcp.app_context import AppContext
from gstarcad_mcp.errors import ExpectedCadError
from gstarcad_mcp.policy.permissions import check_permission
from gstarcad_mcp.runtime.command import CadCommand
from gstarcad_mcp.schemas.entities import EntityRef
from gstarcad_mcp.schemas.tools import EntityQuery, GetEntitiesRequest
from gstarcad_mcp.tools._helpers import (
    decode_cursor,
    encode_cursor,
    get_state,
    map_error,
    run_command,
)

READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)


class LayerListResult(BaseModel):
    document_id: UUID
    layers: list[dict]


class LayoutListResult(BaseModel):
    document_id: UUID
    layouts: list[dict]


class EntityQueryResult(BaseModel):
    document_id: UUID
    revision: int
    entities: list[EntityRef]
    next_cursor: str | None = None
    truncated: bool = False


class GetEntitiesResult(BaseModel):
    document_id: UUID
    entities: list[EntityRef]
    missing_handles: list[str] = Field(default_factory=list)


def register_inspection_tools(mcp) -> None:
    @mcp.tool(
        name="gcad_list_layers",
        title="List layers",
        description=(
            "List normalized layer metadata (name, color, linetype, flags) for one document."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )
    async def gcad_list_layers(ctx: Context[AppContext], document_id: UUID) -> LayerListResult:
        state = get_state(ctx)
        check_permission(state.config.server.permission_profile, "cad.entity.read")
        result = await run_command(state, CadCommand(name="list_layers", document_id=document_id))
        return LayerListResult(document_id=document_id, layers=result["layers"])

    @mcp.tool(
        name="gcad_list_layouts",
        title="List layouts",
        description="List model/paper layouts in tab order for one document.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    async def gcad_list_layouts(
        ctx: Context[AppContext],
        document_id: UUID,
        include_model: bool = Field(default=True),
    ) -> LayoutListResult:
        state = get_state(ctx)
        check_permission(state.config.server.permission_profile, "cad.entity.read")
        result = await run_command(
            state,
            CadCommand(
                name="list_layouts",
                document_id=document_id,
                payload={"include_model": include_model},
            ),
        )
        return LayoutListResult(document_id=document_id, layouts=result["layouts"])

    @mcp.tool(
        name="gcad_query_entities",
        title="Query entities",
        description=(
            "Read normalized entity summaries from one registered document with filtering and "
            "pagination. Use next_cursor to page large drawings. Does not modify geometry."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )
    async def gcad_query_entities(
        ctx: Context[AppContext],
        document_id: UUID,
        layout: str | None = Field(default=None, max_length=255),
        entity_types: list[str] = Field(default_factory=list, max_length=32),
        layers: list[str] = Field(default_factory=list, max_length=64),
        handles: list[str] = Field(default_factory=list, max_length=500),
        text_contains: str | None = Field(default=None, max_length=512),
        cursor: str | None = Field(default=None, max_length=512),
        limit: int = Field(default=200, ge=1, le=1000),
        include_bounds: bool = Field(default=False),
    ) -> EntityQueryResult:
        request = EntityQuery(
            document_id=document_id,
            layout=layout,
            entity_types=entity_types,
            layers=layers,
            handles=handles,
            text_contains=text_contains,
            cursor=cursor,
            limit=limit,
            include_bounds=include_bounds,
        )
        state = get_state(ctx)
        check_permission(state.config.server.permission_profile, "cad.entity.read")
        try:
            state.limits.check_page_size(request.limit)
            state.limits.check_handles(request.handles)
            offset = 0
            if request.cursor:
                offset = decode_cursor(state, request.document_id, request.cursor)
        except ExpectedCadError as exc:
            raise map_error(exc) from exc
        result = await run_command(
            state,
            CadCommand(
                name="query_entities",
                document_id=request.document_id,
                payload={
                    "layout": request.layout,
                    "entity_types": request.entity_types,
                    "layers": request.layers,
                    "handles": request.handles,
                    "text_contains": request.text_contains,
                    "offset": offset,
                    "limit": request.limit,
                    "include_bounds": request.include_bounds,
                },
            ),
        )
        next_offset = result.get("next_offset")
        return EntityQueryResult(
            document_id=request.document_id,
            revision=result.get("revision", 0),
            entities=[EntityRef.model_validate(e) for e in result["entities"]],
            next_cursor=(
                encode_cursor(state, request.document_id, next_offset) if next_offset else None
            ),
            truncated=next_offset is not None,
        )

    @mcp.tool(
        name="gcad_get_entities",
        title="Get entities by handle",
        description=(
            "Fetch richer details for known entity handles. Missing handles are reported in "
            "missing_handles rather than as an error."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )
    async def gcad_get_entities(
        ctx: Context[AppContext],
        document_id: UUID,
        handles: list[str] = Field(min_length=1, max_length=1000),
        detail: Literal["summary", "full"] = Field(default="full"),
    ) -> GetEntitiesResult:
        request = GetEntitiesRequest(document_id=document_id, handles=handles, detail=detail)
        state = get_state(ctx)
        check_permission(state.config.server.permission_profile, "cad.entity.read")
        try:
            state.limits.check_handles(request.handles)
        except ExpectedCadError as exc:
            raise map_error(exc) from exc
        result = await run_command(
            state,
            CadCommand(
                name="get_entities",
                document_id=request.document_id,
                payload={"handles": request.handles},
            ),
        )
        return GetEntitiesResult(
            document_id=request.document_id,
            entities=[EntityRef.model_validate(e) for e in result["entities"]],
            missing_handles=result.get("missing_handles", []),
        )
