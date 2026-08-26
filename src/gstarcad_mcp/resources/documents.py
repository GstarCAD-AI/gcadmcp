"""Status, document, and snapshot resources (§18). Read-only: never mutate CAD state."""

from __future__ import annotations

import json

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError

from gstarcad_mcp.app_context import AppContext
from gstarcad_mcp.errors import ExpectedCadError
from gstarcad_mcp.resources._state import get_current_state
from gstarcad_mcp.runtime.command import CadCommand
from gstarcad_mcp.tools._helpers import get_state
from gstarcad_mcp.util.ids import parse_uuid


def _dumps(obj: object) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)


async def _run(state: AppContext, name: str, payload: dict | None = None, document_id=None):
    try:
        return await state.cad_actor.execute(
            CadCommand(name=name, payload=payload or {}, document_id=document_id)
        )
    except ExpectedCadError as exc:
        raise ResourceNotFoundError(exc.client_message()) from exc


def _parse_document_id(document_id: str):
    try:
        return parse_uuid(document_id, what="document_id")
    except ExpectedCadError as exc:
        raise ResourceNotFoundError(exc.client_message()) from exc


def register_document_resources(mcp: MCPServer) -> None:
    @mcp.resource(
        "gcad://status",
        name="gcad_status",
        mime_type="application/json",
        description="Live GstarCAD connection and document status.",
    )
    async def gcad_status() -> str:
        state = get_current_state()
        try:
            payload = await _run(state, "status")
        except ResourceNotFoundError:
            payload = {}
        payload = {
            **payload,
            "runtime_state": state.cad_actor.state.value,
            "queue_depth": state.cad_actor.queue_depth,
        }
        return _dumps(payload)

    @mcp.resource(
        "gcad://documents",
        name="gcad_documents",
        mime_type="application/json",
        description="Registry of known documents with ids and revisions.",
    )
    async def gcad_documents() -> str:
        return _dumps(await _run(get_current_state(), "list_documents"))

    @mcp.resource(
        "gcad://documents/{document_id}/summary",
        name="gcad_document_summary",
        mime_type="application/json",
        description="Summary of a single registered document.",
    )
    async def document_summary(document_id: str, ctx: Context) -> str:
        doc_id = _parse_document_id(document_id)
        result = await _run(get_state(ctx), "list_documents")
        for doc in result.get("documents", []):
            if doc.get("document_id") == str(doc_id):
                return _dumps(doc)
        raise ResourceNotFoundError(f"Document not found: {document_id}")

    @mcp.resource(
        "gcad://documents/{document_id}/layers",
        name="gcad_document_layers",
        mime_type="application/json",
        description="Layer table of a document.",
    )
    async def document_layers(document_id: str, ctx: Context) -> str:
        doc_id = _parse_document_id(document_id)
        return _dumps(await _run(get_state(ctx), "list_layers", document_id=doc_id))

    @mcp.resource(
        "gcad://documents/{document_id}/layouts",
        name="gcad_document_layouts",
        mime_type="application/json",
        description="Layout list of a document.",
    )
    async def document_layouts(document_id: str, ctx: Context) -> str:
        doc_id = _parse_document_id(document_id)
        return _dumps(await _run(get_state(ctx), "list_layouts", document_id=doc_id))

    @mcp.resource(
        "gcad://documents/{document_id}/entities/{handle}",
        name="gcad_document_entity",
        mime_type="application/json",
        description="A single entity by handle.",
    )
    async def document_entity(document_id: str, handle: str, ctx: Context) -> str:
        doc_id = _parse_document_id(document_id)
        result = await _run(
            get_state(ctx), "get_entities", payload={"handles": [handle]}, document_id=doc_id
        )
        entities = result.get("entities", [])
        if not entities:
            raise ResourceNotFoundError(f"Entity not found: {handle}")
        return _dumps(entities[0])

    @mcp.resource(
        "gcad://documents/{document_id}/snapshot/latest",
        name="gcad_document_snapshot_latest",
        mime_type="image/png",
        description="Most recently cached view capture for a document.",
    )
    async def document_snapshot_latest(document_id: str, ctx: Context) -> bytes:
        doc_id = _parse_document_id(document_id)
        state = get_state(ctx)
        prefix = f"{doc_id}-"
        candidates = [p for p in state.workspace.cache_dir.glob(f"{prefix}*.png") if p.is_file()]
        if not candidates:
            raise ResourceNotFoundError(f"No cached snapshot for document: {document_id}")
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        data = latest.read_bytes()
        cap = state.limits.limits.max_resource_bytes
        if len(data) > cap:
            raise ResourceNotFoundError("Snapshot exceeds the resource size limit.")
        return data
