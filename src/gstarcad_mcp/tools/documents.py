"""Document lifecycle tools (§16.2-16.7)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from gstarcad_mcp.app_context import AppContext
from gstarcad_mcp.errors import (
    DOCUMENT_OWNERSHIP_DENIED,
    INVALID_ACTION,
    ExpectedCadError,
)
from gstarcad_mcp.policy.permissions import check_external_document_action, check_permission
from gstarcad_mcp.runtime.command import CadCommand
from gstarcad_mcp.schemas.documents import DocumentOperationResult, DocumentRef
from gstarcad_mcp.schemas.results import SnapshotResult  # noqa: F401  (shared module import)
from gstarcad_mcp.schemas.tools import (
    ActivateDocumentRequest,
    CloseDocumentRequest,
    NewDocumentRequest,
    OpenDocumentRequest,
    SaveDocumentRequest,
)
from gstarcad_mcp.tools._helpers import get_state, map_error, run_command, with_idempotency

READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
MUTATING = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)


class DocumentListResult(BaseModel):
    runtime_id: UUID
    active_document_id: UUID | None = None
    documents: list[DocumentRef]


class CloseDocumentResult(BaseModel):
    document_id: UUID
    closed: bool
    saved_before_close: bool


class SaveDocumentResult(BaseModel):
    document: DocumentRef
    saved_path_relative: str | None = None
    byte_size: int | None = None
    modified_at: float | None = None


def register_document_tools(mcp) -> None:
    @mcp.tool(
        name="gcad_list_documents",
        title="List open documents",
        description=(
            "List registered open GstarCAD documents with server document ids, ownership, "
            "revisions, and the active document. Read-only."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )
    async def gcad_list_documents(
        ctx: Context[AppContext], refresh: bool = Field(default=True)
    ) -> DocumentListResult:
        state = get_state(ctx)
        check_permission(state.config.server.permission_profile, "cad.document.read")
        result = await run_command(
            state, CadCommand(name="list_documents", payload={"refresh": refresh})
        )
        return DocumentListResult(
            runtime_id=state.runtime_id,
            active_document_id=result.get("active_document_id"),
            documents=[DocumentRef.model_validate(d) for d in result["documents"]],
        )

    @mcp.tool(
        name="gcad_new_document",
        title="Create a new drawing",
        description=(
            "Create a new server-owned GstarCAD drawing, optionally from a workspace template. "
            "Idempotent by operation_id."
        ),
        annotations=MUTATING,
        structured_output=True,
    )
    async def gcad_new_document(
        ctx: Context[AppContext],
        operation_id: UUID,
        template_relative_path: str | None = Field(default=None, max_length=1024),
        activate: bool = Field(default=True),
    ) -> DocumentOperationResult:
        request = NewDocumentRequest(
            operation_id=operation_id,
            template_relative_path=template_relative_path,
            activate=activate,
        )
        state = get_state(ctx)
        profile = state.config.server.permission_profile
        try:
            check_permission(profile, "cad.document.create")
        except ExpectedCadError as exc:
            raise map_error(exc) from exc
        template_path = None
        if request.template_relative_path:
            try:
                template_path = str(
                    state.workspace.resolve_input(
                        request.template_relative_path, allowed_extensions={".dwt", ".dwg", ".dxf"}
                    )
                )
            except ExpectedCadError as exc:
                raise map_error(exc) from exc

        async def execute():
            ref = await run_command(
                state,
                CadCommand(name="new_document", payload={"template_path": template_path}),
            )
            return DocumentOperationResult(
                runtime_id=state.runtime_id,
                document=DocumentRef.model_validate(ref),
                operation_id=request.operation_id,
            )

        return await with_idempotency(
            state,
            tool_name="gcad_new_document",
            operation_id=request.operation_id,
            document_id=None,
            arguments=request.model_dump(mode="json"),
            result_model=DocumentOperationResult.model_validate,
            execute=execute,
        )

    @mcp.tool(
        name="gcad_open_document",
        title="Open a drawing from the workspace",
        description=(
            "Open an existing DWG/DXF from the workspace inputs. Idempotent by operation_id; "
            "reopening the same canonical path returns the registered document."
        ),
        annotations=MUTATING,
        structured_output=True,
    )
    async def gcad_open_document(
        ctx: Context[AppContext],
        operation_id: UUID,
        path: str = Field(min_length=1, max_length=1024),
        read_only: bool = Field(default=False),
        activate: bool = Field(default=True),
    ) -> DocumentOperationResult:
        request = OpenDocumentRequest(
            operation_id=operation_id,
            input_relative_path=path,
            read_only=read_only,
            activate=activate,
        )
        state = get_state(ctx)
        profile = state.config.server.permission_profile
        try:
            check_permission(profile, "cad.document.open")
            resolved = state.workspace.resolve_input(request.input_relative_path)
        except ExpectedCadError as exc:
            raise map_error(exc) from exc

        async def execute():
            ref = await run_command(
                state,
                CadCommand(
                    name="open_document",
                    payload={"path": str(resolved), "read_only": request.read_only},
                ),
            )
            document = DocumentRef.model_validate(ref)
            document.relative_path = request.input_relative_path
            return DocumentOperationResult(
                runtime_id=state.runtime_id,
                document=document,
                operation_id=request.operation_id,
            )

        return await with_idempotency(
            state,
            tool_name="gcad_open_document",
            operation_id=request.operation_id,
            document_id=None,
            arguments={"path": request.input_relative_path, "read_only": request.read_only},
            result_model=DocumentOperationResult.model_validate,
            execute=execute,
        )

    @mcp.tool(
        name="gcad_activate_document",
        title="Activate a document",
        description="Make a registered document the active GstarCAD document. Idempotent.",
        annotations=MUTATING,
        structured_output=True,
    )
    async def gcad_activate_document(
        ctx: Context[AppContext],
        document_id: UUID,
        expected_revision: int | None = Field(default=None, ge=0),
    ) -> DocumentOperationResult:
        request = ActivateDocumentRequest(
            document_id=document_id, expected_revision=expected_revision
        )
        state = get_state(ctx)
        check_permission(state.config.server.permission_profile, "cad.document.read")
        ref = await run_command(
            state,
            CadCommand(name="activate_document", document_id=request.document_id),
        )
        return DocumentOperationResult(
            runtime_id=state.runtime_id, document=DocumentRef.model_validate(ref)
        )

    @mcp.tool(
        name="gcad_save_document",
        title="Save a document",
        description=(
            "Save a document in place or to a workspace-relative output path (save_as). "
            "Saving external documents in place is profile-restricted; overwrite is destructive."
        ),
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    async def gcad_save_document(
        ctx: Context[AppContext],
        operation_id: UUID,
        document_id: UUID,
        expected_revision: int | None = Field(default=None, ge=0),
        mode: Literal["save", "save_as"] = Field(default="save"),
        output_relative_path: str | None = Field(default=None, max_length=1024),
        overwrite: bool = Field(default=False),
    ) -> SaveDocumentResult:
        request = SaveDocumentRequest(
            operation_id=operation_id,
            document_id=document_id,
            expected_revision=expected_revision,
            mode=mode,
            output_relative_path=output_relative_path,
            overwrite=overwrite,
        )
        state = get_state(ctx)
        profile = state.config.server.permission_profile
        try:
            check_permission(profile, "cad.document.save")
            entry_ref = None
            docs = await run_command(state, CadCommand(name="list_documents", payload={}))
            for doc in docs["documents"]:
                if doc["document_id"] == str(request.document_id):
                    entry_ref = DocumentRef.model_validate(doc)
            if entry_ref is None:
                raise ExpectedCadError(
                    "DOCUMENT_NOT_FOUND", "Unknown document_id; call gcad_list_documents."
                )
            if entry_ref.ownership.value == "external" and request.mode == "save":
                check_external_document_action(profile, "save_in_place")
            output_path = None
            relative = None
            if request.mode == "save_as":
                if not request.output_relative_path:
                    raise ExpectedCadError(INVALID_ACTION, "save_as requires output_relative_path.")
                resolved = state.workspace.resolve_output(
                    request.output_relative_path, overwrite=request.overwrite
                )
                output_path = str(resolved)
                relative = request.output_relative_path
        except ExpectedCadError as exc:
            raise map_error(exc) from exc

        async def execute():
            result = await run_command(
                state,
                CadCommand(
                    name="save_document",
                    document_id=request.document_id,
                    expected_revision=request.expected_revision,
                    payload={
                        "mode": request.mode,
                        "output_path": output_path,
                        "relative_path": relative,
                    },
                ),
            )
            state.audit.record(
                "cad.document.save",
                document_id=str(request.document_id),
                mode=request.mode,
                path=relative,
                overwrite=request.overwrite,
            )
            return SaveDocumentResult.model_validate(result)

        return await with_idempotency(
            state,
            tool_name="gcad_save_document",
            operation_id=request.operation_id,
            document_id=request.document_id,
            arguments=request.model_dump(mode="json"),
            result_model=SaveDocumentResult.model_validate,
            execute=execute,
        )

    @mcp.tool(
        name="gcad_close_document",
        title="Close a server-owned document",
        description=(
            "Close a server-owned document. External documents are denied by default. "
            "save_policy 'discard' is destructive."
        ),
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    async def gcad_close_document(
        ctx: Context[AppContext],
        operation_id: UUID,
        document_id: UUID,
        save_policy: Literal["reject_dirty", "save", "discard"] = Field(default="reject_dirty"),
    ) -> CloseDocumentResult:
        request = CloseDocumentRequest(
            operation_id=operation_id,
            document_id=document_id,
            save_policy=save_policy,
        )
        state = get_state(ctx)
        profile = state.config.server.permission_profile
        try:
            check_permission(profile, "cad.document.close")
            docs = await run_command(state, CadCommand(name="list_documents", payload={}))
            target = None
            for doc in docs["documents"]:
                if doc["document_id"] == str(request.document_id):
                    target = DocumentRef.model_validate(doc)
            if target is None:
                raise ExpectedCadError(
                    "DOCUMENT_NOT_FOUND", "Unknown document_id; call gcad_list_documents."
                )
            if target.ownership.value == "external":
                raise ExpectedCadError(
                    DOCUMENT_OWNERSHIP_DENIED, "Closing external documents is denied by default."
                )
            if request.save_policy == "discard":
                check_external_document_action(profile, "discard")
        except ExpectedCadError as exc:
            raise map_error(exc) from exc

        async def execute():
            result = await run_command(
                state,
                CadCommand(
                    name="close_document",
                    document_id=request.document_id,
                    payload={"save_policy": request.save_policy},
                ),
            )
            state.audit.record(
                "cad.document.close",
                document_id=str(request.document_id),
                save_policy=request.save_policy,
            )
            return CloseDocumentResult(document_id=request.document_id, **result)

        return await with_idempotency(
            state,
            tool_name="gcad_close_document",
            operation_id=request.operation_id,
            document_id=request.document_id,
            arguments=request.model_dump(mode="json"),
            result_model=CloseDocumentResult.model_validate,
            execute=execute,
        )
