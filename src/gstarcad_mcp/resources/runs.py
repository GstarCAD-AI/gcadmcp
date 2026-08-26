"""Run and evidence resources (§18)."""

from __future__ import annotations

from uuid import UUID

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError

from gstarcad_mcp.app_context import AppContext
from gstarcad_mcp.errors import ExpectedCadError
from gstarcad_mcp.tools._helpers import get_state
from gstarcad_mcp.util.ids import parse_uuid, validate_slug

_ARTIFACTS = {
    "brief": ("brief.md", "text/markdown"),
    "actions": ("actions.jsonl", "application/x-ndjson"),
    "before-entities": ("before_entities.json", "application/json"),
    "after-entities": ("after_entities.json", "application/json"),
    "feedback": ("feedback.md", "text/markdown"),
    "validation": ("validation.json", "application/json"),
}


def _parse_run_id(run_id: str) -> UUID:
    try:
        return parse_uuid(run_id, what="run_id")
    except ExpectedCadError as exc:
        raise ResourceNotFoundError(f"Run not found: {exc.code}") from exc


def _read_text(state: AppContext, run_id: UUID, artifact: str) -> str:
    try:
        path = state.run_store.artifact_path(run_id, artifact)
        return path.read_text(encoding="utf-8")
    except ExpectedCadError:
        raise ResourceNotFoundError(f"Run artifact not found: {artifact}") from None
    except (FileNotFoundError, OSError, UnicodeDecodeError) as exc:
        raise ResourceNotFoundError(f"Run artifact not found: {artifact}") from exc


def _check_size(state: AppContext, data: bytes) -> bytes:
    cap = state.limits.limits.max_resource_bytes
    if len(data) > cap:
        raise ResourceNotFoundError("Resource exceeds the configured size limit.")
    return data


def register_run_resources(mcp: MCPServer) -> None:
    @mcp.resource(
        "gcad://runs/{run_id}/manifest",
        name="gcad_run_manifest",
        mime_type="application/json",
        description="Run manifest with status, artifacts, and validations.",
    )
    async def run_manifest(run_id: str, ctx: Context) -> str:
        state = get_state(ctx)
        rid = _parse_run_id(run_id)
        try:
            manifest = state.run_store.read_manifest(rid)
        except ExpectedCadError as exc:
            raise ResourceNotFoundError(f"Run manifest not found: {run_id} ({exc.code})") from exc
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise ResourceNotFoundError(f"Run manifest not found: {run_id}") from exc
        return manifest.model_dump_json(indent=2)

    for slug, (filename, mime) in _ARTIFACTS.items():

        def _make_handler(fname: str):
            async def handler(run_id: str, ctx: Context) -> str:
                return _read_text(get_state(ctx), _parse_run_id(run_id), fname)

            return handler

        mcp.resource(
            f"gcad://runs/{{run_id}}/{slug}",
            name=f"gcad_run_{slug.replace('-', '_')}",
            mime_type=mime,
            description=f"Run artifact: {filename}.",
        )(_make_handler(filename))

    @mcp.resource(
        "gcad://runs/{run_id}/snapshots/{name}",
        name="gcad_run_snapshot",
        mime_type="image/png",
        description="PNG screenshot captured during a run.",
    )
    async def run_snapshot(run_id: str, name: str, ctx: Context) -> bytes:
        state = get_state(ctx)
        rid = _parse_run_id(run_id)
        try:
            slug = validate_slug(name, what="snapshot name")
        except ExpectedCadError as exc:
            raise ResourceNotFoundError(exc.client_message()) from exc
        try:
            path = state.run_store.snapshot_path(rid, slug)
        except ExpectedCadError as exc:
            raise ResourceNotFoundError(exc.client_message()) from exc
        if not path.exists():
            raise ResourceNotFoundError(f"Snapshot not found: {name}")
        return _check_size(state, path.read_bytes())
