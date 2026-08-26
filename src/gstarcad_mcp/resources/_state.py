"""Lifespan-bound state access for static resources (SDK v2 injects Context only into templates)."""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ResourceError

from gstarcad_mcp.app_context import AppContext

_current: AppContext | None = None


def set_current_state(state: AppContext | None) -> None:
    global _current
    _current = state


def get_current_state() -> AppContext:
    if _current is None:
        raise ResourceError("Server state is not initialized.")
    return _current
