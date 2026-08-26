"""Server factory and typed lifespan (§13)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer

from gstarcad_mcp import SERVER_NAME, SERVER_VERSION
from gstarcad_mcp.app_context import AppContext
from gstarcad_mcp.config import ServerConfig, load_config
from gstarcad_mcp.logging_config import AuditLogger, configure_logging
from gstarcad_mcp.policy.idempotency import IdempotencyStore
from gstarcad_mcp.policy.limits import LimitsPolicy
from gstarcad_mcp.policy.workspace import WorkspacePolicy
from gstarcad_mcp.prompts import register_prompts
from gstarcad_mcp.resources import register_document_resources, register_run_resources
from gstarcad_mcp.resources._state import set_current_state
from gstarcad_mcp.runs.store import RunStore
from gstarcad_mcp.runtime.cad_actor import ActorRuntimeState, CadActor
from gstarcad_mcp.runtime.dispatcher import CadDispatcher
from gstarcad_mcp.runtime.document_registry import DocumentRegistry
from gstarcad_mcp.runtime.lifecycle import runtime_id
from gstarcad_mcp.schemas.documents import DocumentOwnership
from gstarcad_mcp.tools import (
    register_document_tools,
    register_editing_tools,
    register_evidence_tools,
    register_inspection_tools,
    register_status_tools,
)

logger = logging.getLogger(__name__)

_INSTRUCTIONS = (
    "GstarCAD 2D drawing automation. Use gcad_get_status first; mutations require a "
    "document and run; every drawing task ends with evidence (entities, screenshot, "
    "saved DWG). Partial results must be reported honestly."
)


@asynccontextmanager
async def app_lifespan(
    server: MCPServer, config: ServerConfig, *, cad_factory: Callable[[], Any] | None = None
) -> AsyncIterator[AppContext]:
    workspace = WorkspacePolicy(
        config.workspace_root(),
        allow_unc=config.workspace.allow_unc,
        allow_overwrite=config.workspace.allow_overwrite,
    )
    workspace.ensure_layout()
    configure_logging(
        config.server.log_level,
        file_path=workspace.logs_dir / "server.log" if config.logging.file_enabled else None,
        max_bytes=config.logging.max_file_bytes,
        backup_count=config.logging.backup_count,
    )

    run_store = RunStore(workspace.runs_dir)
    idempotency = IdempotencyStore(
        workspace.state_dir,
        retention_days=config.idempotency.retention_days,
        max_records=config.idempotency.max_records,
    )
    audit = AuditLogger(workspace.logs_dir / "audit.jsonl")
    limits = LimitsPolicy(config.limits)

    def journal_writer(row: dict[str, Any]) -> None:
        raw_run_id = row.get("run_id")
        if not raw_run_id:
            return
        try:
            run_store.append_action(uuid.UUID(str(raw_run_id)), row)
        except Exception:
            logger.exception("Failed to journal action for run %s", raw_run_id)

    registry = DocumentRegistry()
    dispatcher = CadDispatcher(journal_writer=journal_writer)

    def runtime_state_factory(
        cad: Any, reg: DocumentRegistry, actor_config: Any
    ) -> ActorRuntimeState:
        state = ActorRuntimeState(cad, reg, actor_config)
        try:
            reg.discover(cad.app, ownership=DocumentOwnership.EXTERNAL)
        except Exception:
            logger.exception("Document discovery on startup failed")
        return state

    actor = CadActor(
        config.cad,
        dispatcher,
        cad_factory=cad_factory,
        registry=registry,
        runtime_state_factory=runtime_state_factory,
    )

    cad_startup_error: str | None = None
    try:
        await actor.start()
    except Exception as exc:
        cad_startup_error = str(exc)
        logger.warning("CAD actor startup failed; entering degraded mode: %s", exc)

    state = AppContext(
        config=config,
        cad_actor=actor,
        run_store=run_store,
        workspace=workspace,
        idempotency=idempotency,
        audit=audit,
        limits=limits,
        runtime_id=runtime_id(),
        cad_startup_error=cad_startup_error,
    )
    set_current_state(state)
    try:
        yield state
    finally:
        set_current_state(None)
        await actor.close()


def _reject_unknown_arguments(mcp: MCPServer) -> None:
    """Reject unknown top-level tool arguments at the protocol boundary (§31.1).

    The SDK builds one dynamic pydantic argument model per tool with the default
    ``extra='ignore'`` behaviour; unknown fields must instead produce a validation
    error so misspelled arguments never vanish silently.
    """
    for tool in mcp._tool_manager.list_tools():
        arg_model = tool.fn_metadata.arg_model
        arg_model.model_config["extra"] = "forbid"
        arg_model.model_rebuild(force=True)


def create_server(
    config: ServerConfig | None = None, *, cad_factory: Callable[[], Any] | None = None
) -> MCPServer:
    cfg = config or load_config()

    @asynccontextmanager
    async def lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
        async with app_lifespan(server, cfg, cad_factory=cad_factory) as state:
            yield state

    mcp: MCPServer = MCPServer(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        instructions=_INSTRUCTIONS,
        lifespan=lifespan,
    )
    register_status_tools(mcp)
    register_document_tools(mcp)
    register_inspection_tools(mcp)
    register_editing_tools(mcp)
    register_evidence_tools(mcp)
    register_document_resources(mcp)
    register_run_resources(mcp)
    register_prompts(mcp)
    _reject_unknown_arguments(mcp)
    return mcp
