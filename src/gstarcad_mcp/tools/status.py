"""gcad_get_status — works even when GstarCAD startup failed (§16.1)."""

from __future__ import annotations

import platform
import sys

from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from gstarcad_mcp import SERVER_VERSION
from gstarcad_mcp.app_context import AppContext
from gstarcad_mcp.errors import ExpectedCadError
from gstarcad_mcp.runtime.command import CadCommand
from gstarcad_mcp.runtime.health import RuntimeState
from gstarcad_mcp.schemas.results import GcadStatusResult
from gstarcad_mcp.tools._helpers import get_state


def _probe_gstarcad() -> tuple[bool | None, bool | None]:
    if sys.platform != "win32":
        return False, False
    try:
        from pygcadwin._com import registered_gstarcad_prog_ids

        ids = list(registered_gstarcad_prog_ids())
        return (True, bool(ids)) if ids else (False, False)
    except Exception:
        return None, None


def register_status_tools(mcp) -> None:
    @mcp.tool(
        name="gcad_get_status",
        title="GstarCAD server status",
        description=(
            "Return server, runtime, platform, GstarCAD, protocol, and capability status. "
            "Read-only and safe to call first; it works even when GstarCAD startup failed, "
            "returning a diagnosis instead of raising."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    async def gcad_get_status(
        ctx: Context[AppContext],
        include_diagnostics: bool = Field(default=False),
    ) -> GcadStatusResult:
        state = get_state(ctx)
        config = state.config
        gstarcad_installed, com_registered = _probe_gstarcad()
        actor = state.cad_actor
        actor_state = actor.state
        warnings: list[str] = []
        cad_info: dict = {}

        if actor_state == RuntimeState.READY:
            try:
                cad_info = await actor.execute(CadCommand(name="status"))
            except ExpectedCadError as exc:
                warnings.append(exc.client_message())
        elif state.cad_startup_error:
            warnings.append(f"GstarCAD startup failed: {state.cad_startup_error}")
        if sys.platform != "win32":
            warnings.append("PLATFORM_UNSUPPORTED: live CAD requires Windows.")

        try:
            import mcp

            sdk_version = getattr(mcp, "__version__", "2.x")
        except Exception:
            sdk_version = "2.x"

        return GcadStatusResult(
            server_version=SERVER_VERSION,
            runtime_id=state.runtime_id,
            protocol_sdk_version=f"mcp-python {sdk_version}",
            platform=f"{platform.system()} {platform.release()} {platform.machine()}",
            permission_profile=config.server.permission_profile,
            runtime_state=actor_state.value,
            queue_depth=actor.queue_depth,
            gstarcad_installed=gstarcad_installed,
            com_registered=com_registered,
            connected=bool(cad_info.get("connected", False)),
            connected_prog_id=cad_info.get("connected_prog_id"),
            connection_mode=cad_info.get("connection_mode"),
            application_responsive=cad_info.get("application_responsive"),
            active_document_id=cad_info.get("active_document_id"),
            document_count=int(cad_info.get("document_count", 0)),
            screenshot_available=sys.platform == "win32",
            transaction_modes=["best_effort"],
            external_change_detection="not_available",
            startup_error=state.cad_startup_error if include_diagnostics or True else None,
            warnings=warnings,
        )
