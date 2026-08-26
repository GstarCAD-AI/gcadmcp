"""Shared helpers for tool handlers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from gstarcad_mcp.app_context import AppContext
from gstarcad_mcp.errors import INVALID_ACTION, ExpectedCadError


# Bare-Context call sites included: the MCP SDK's resource context injection
# only detects the unparameterized Context class, so resource handlers cannot
# use Context[AppContext].
def get_state(ctx: Context[Any]) -> AppContext:
    return ctx.request_context.lifespan_context


def map_error(exc: ExpectedCadError) -> ToolError:
    return ToolError(exc.client_message())


async def run_command(state: AppContext, command: Any) -> Any:
    try:
        return await state.cad_actor.execute(command)
    except ExpectedCadError as exc:
        raise map_error(exc) from exc


async def with_idempotency(
    state: AppContext,
    *,
    tool_name: str,
    operation_id: UUID,
    document_id: UUID | None,
    arguments: dict[str, Any],
    result_model: Callable[[dict], Any] | None,
    execute: Callable[[], Awaitable[Any]],
) -> Any:
    """Idempotent mutation envelope (§21)."""
    try:
        prior = state.idempotency.begin(tool_name, document_id, operation_id, arguments)
        if prior is not None and prior.state != "failed":
            if prior.state in {"succeeded", "partial"} and prior.result_json is not None:
                return result_model(prior.result_json) if result_model else prior.result_json
            state.idempotency.require_replay(prior)  # raises: uncertain / in-progress
        # prior is None (first sight) or a failed attempt we may retry.
    except ExpectedCadError as exc:
        raise map_error(exc) from exc
    try:
        result = await execute()
    except ToolError:
        state.idempotency.complete(tool_name, document_id, operation_id, "failed", None)
        raise
    except ExpectedCadError as exc:
        state.idempotency.complete(tool_name, document_id, operation_id, "failed", None)
        raise map_error(exc) from exc
    payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    final_state = (
        "partial"
        if isinstance(payload, dict) and payload.get("status") == "partial"
        else "succeeded"
    )
    state.idempotency.complete(tool_name, document_id, operation_id, final_state, payload)
    return result


def encode_cursor(state: AppContext, document_id: UUID, offset: int) -> str:
    body = json.dumps({"d": str(document_id), "o": offset}, sort_keys=True)
    sig = hmac.new(state.cursor_secret, body.encode(), hashlib.sha256).hexdigest()[:16]
    return base64.urlsafe_b64encode(f"{body}|{sig}".encode()).decode()


def decode_cursor(state: AppContext, document_id: UUID, cursor: str) -> int:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        body, sig = raw.rsplit("|", 1)
        expected = hmac.new(state.cursor_secret, body.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        data = json.loads(body)
        if data.get("d") != str(document_id):
            raise ValueError("cursor for different document")
        return int(data["o"])
    except Exception as exc:
        raise ExpectedCadError(INVALID_ACTION, "Invalid or tampered cursor.") from exc
