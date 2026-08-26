"""Typed lifespan context shared by all handlers (§13.1)."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from uuid import UUID

from gstarcad_mcp.config import ServerConfig
from gstarcad_mcp.logging_config import AuditLogger
from gstarcad_mcp.policy.idempotency import IdempotencyStore
from gstarcad_mcp.policy.limits import LimitsPolicy
from gstarcad_mcp.policy.workspace import WorkspacePolicy
from gstarcad_mcp.runs.store import RunStore
from gstarcad_mcp.runtime.cad_actor import CadActor


@dataclass
class AppContext:
    config: ServerConfig
    cad_actor: CadActor
    run_store: RunStore
    workspace: WorkspacePolicy
    idempotency: IdempotencyStore
    audit: AuditLogger
    limits: LimitsPolicy
    runtime_id: UUID
    cursor_secret: bytes = field(default_factory=lambda: secrets.token_bytes(32))
    cad_startup_error: str | None = None
