"""Editing tools: layers, entity creation, and the batch action engine (§16.12-16.14)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from gstarcad_mcp.app_context import AppContext
from gstarcad_mcp.errors import INVALID_ACTION, ExpectedCadError
from gstarcad_mcp.policy.permissions import check_permission
from gstarcad_mcp.policy.revisions import check_expected_revision
from gstarcad_mcp.runtime.command import CadCommand
from gstarcad_mcp.schemas.results import BatchOperationResult
from gstarcad_mcp.schemas.tools import (
    ApplyActionsRequest,
    CadAction,
    CreateEntitiesRequest,
    EnsureLayerAction,
    EnsureLayersRequest,
    LayerSpec,
)
from gstarcad_mcp.tools._helpers import get_state, map_error, run_command, with_idempotency

_OP_PERMISSIONS = {
    "ensure_layer": "cad.layer.create",
    "regen": "cad.view.modify",
    "zoom_extents": "cad.view.modify",
}

MUTATING = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
BATCH = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False
)


class EnsureLayersResult(BaseModel):
    document_id: object
    revision_before: int
    revision_after: int
    layers: list[dict]


async def _current_revision(state: AppContext, document_id) -> int:
    docs = await run_command(state, CadCommand(name="list_documents", payload={}))
    for doc in docs["documents"]:
        if doc["document_id"] == str(document_id):
            return int(doc["revision"])
    raise ExpectedCadError("DOCUMENT_NOT_FOUND", "Unknown document_id; call gcad_list_documents.")


def _action_dicts(actions: list[Any]) -> list[dict]:
    return [a.model_dump(mode="json") if hasattr(a, "model_dump") else dict(a) for a in actions]


async def _execute_batch(state: AppContext, request: ApplyActionsRequest) -> BatchOperationResult:
    profile = state.config.server.permission_profile
    actions = _action_dicts(request.actions)
    for action in actions:
        op = action.get("op")
        default = "cad.entity.create"
        permission = _OP_PERMISSIONS.get(op, default) if isinstance(op, str) else default
        check_permission(profile, permission)
    state.limits.check_batch(actions)
    revision = await _current_revision(state, request.document_id)
    check_expected_revision(
        request.expected_revision, revision, document_label=str(request.document_id)
    )
    result = await run_command(
        state,
        CadCommand(
            name="apply_actions",
            document_id=request.document_id,
            expected_revision=request.expected_revision,
            run_id=request.run_id,
            operation_id=request.operation_id,
            payload={
                "actions": actions,
                "atomic": request.atomic,
                "stop_on_error": request.stop_on_error,
            },
        ),
    )
    batch = BatchOperationResult.model_validate(result)
    failed = [a for a in batch.actions if a.status == "failed"]
    succeeded = [a for a in batch.actions if a.status == "succeeded"]
    state.audit.record(
        "cad.batch",
        operation_id=str(request.operation_id),
        document_id=str(request.document_id),
        run_id=str(request.run_id) if request.run_id else None,
        status=batch.status,
        succeeded=len(succeeded),
        failed=len(failed),
        transaction_mode=batch.transaction_mode,
    )
    if failed and not succeeded:
        first = failed[0].error
        message = first.message if first else "Batch failed before any mutation."
        raise ToolError(f"{INVALID_ACTION}: {message}")
    return batch


def register_editing_tools(mcp) -> None:
    @mcp.tool(
        name="gcad_ensure_layers",
        title="Ensure layers exist",
        description=(
            "Create or update several layers in one call. Mutating but non-destructive and "
            "idempotent for identical specs."
        ),
        annotations=MUTATING,
        structured_output=True,
    )
    async def gcad_ensure_layers(
        ctx: Context[AppContext],
        operation_id: UUID,
        document_id: UUID,
        expected_revision: int | None = Field(default=None, ge=0),
        layers: list[LayerSpec] = Field(min_length=1, max_length=200),
    ) -> BatchOperationResult:
        request = EnsureLayersRequest(
            operation_id=operation_id,
            document_id=document_id,
            expected_revision=expected_revision,
            layers=layers,
        )
        state = get_state(ctx)
        batch_request = ApplyActionsRequest(
            operation_id=request.operation_id,
            document_id=request.document_id,
            expected_revision=request.expected_revision,
            atomic=False,
            stop_on_error=True,
            actions=[EnsureLayerAction(name=s.name, color=s.color) for s in request.layers],
        )

        async def execute():
            return await _execute_batch(state, batch_request)

        try:
            return await with_idempotency(
                state,
                tool_name="gcad_ensure_layers",
                operation_id=request.operation_id,
                document_id=request.document_id,
                arguments=request.model_dump(mode="json"),
                result_model=BatchOperationResult.model_validate,
                execute=execute,
            )
        except ExpectedCadError as exc:
            raise map_error(exc) from exc

    @mcp.tool(
        name="gcad_create_entities",
        title="Create entities",
        description=(
            "Create a list of supported entities in one batch. Internally executed through the "
            "same action engine as gcad_apply_actions. Idempotent by operation_id."
        ),
        annotations=MUTATING,
        structured_output=True,
    )
    async def gcad_create_entities(
        ctx: Context[AppContext],
        operation_id: UUID,
        document_id: UUID,
        expected_revision: int | None = Field(default=None, ge=0),
        entities: list[CadAction] = Field(min_length=1, max_length=500),
    ) -> BatchOperationResult:
        request = CreateEntitiesRequest(
            operation_id=operation_id,
            document_id=document_id,
            expected_revision=expected_revision,
            entities=entities,
        )
        state = get_state(ctx)
        batch_request = ApplyActionsRequest(
            operation_id=request.operation_id,
            document_id=request.document_id,
            expected_revision=request.expected_revision,
            atomic=True,
            stop_on_error=True,
            actions=request.entities,
        )

        async def execute():
            return await _execute_batch(state, batch_request)

        try:
            return await with_idempotency(
                state,
                tool_name="gcad_create_entities",
                operation_id=request.operation_id,
                document_id=request.document_id,
                arguments=request.model_dump(mode="json"),
                result_model=BatchOperationResult.model_validate,
                execute=execute,
            )
        except ExpectedCadError as exc:
            raise map_error(exc) from exc

    @mcp.tool(
        name="gcad_apply_actions",
        title="Apply a batch of typed actions",
        description=(
            "Primary tool for complex deterministic edits. Prevalidates every action, checks "
            "permission and revision, executes sequentially in the COM actor, and reports exact "
            "per-action outcomes. Mutating and potentially destructive depending on the batch; "
            "atomicity is reported honestly (transaction_mode), never assumed."
        ),
        annotations=BATCH,
        structured_output=True,
    )
    async def gcad_apply_actions(
        ctx: Context[AppContext],
        operation_id: UUID,
        document_id: UUID,
        run_id: UUID | None = Field(default=None),
        expected_revision: int | None = Field(default=None, ge=0),
        atomic: bool = Field(default=True),
        stop_on_error: bool = Field(default=True),
        actions: list[CadAction] = Field(min_length=1, max_length=500),
    ) -> BatchOperationResult:
        request = ApplyActionsRequest(
            operation_id=operation_id,
            run_id=run_id,
            document_id=document_id,
            expected_revision=expected_revision,
            atomic=atomic,
            stop_on_error=stop_on_error,
            actions=actions,
        )
        state = get_state(ctx)

        async def execute():
            return await _execute_batch(state, request)

        try:
            return await with_idempotency(
                state,
                tool_name="gcad_apply_actions",
                operation_id=request.operation_id,
                document_id=request.document_id,
                arguments=request.model_dump(mode="json"),
                result_model=BatchOperationResult.model_validate,
                execute=execute,
            )
        except ExpectedCadError as exc:
            raise map_error(exc) from exc
