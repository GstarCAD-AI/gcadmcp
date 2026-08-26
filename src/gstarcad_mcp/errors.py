"""Domain error codes, exception hierarchy, and MCP error mapping.

Client-visible messages never contain stack traces, absolute user paths, or
COM representations (guideline 24.4).
"""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError
from mcp.shared.exceptions import MCPError

# --- stable domain error codes (guideline 24.1) ---
PLATFORM_UNSUPPORTED = "PLATFORM_UNSUPPORTED"
GSTARCAD_NOT_INSTALLED = "GSTARCAD_NOT_INSTALLED"
COM_NOT_REGISTERED = "COM_NOT_REGISTERED"
CAD_CONNECTION_FAILED = "CAD_CONNECTION_FAILED"
CAD_STARTUP_TIMEOUT = "CAD_STARTUP_TIMEOUT"
CAD_DISCONNECTED = "CAD_DISCONNECTED"
CAD_NOT_RESPONDING = "CAD_NOT_RESPONDING"
CAD_QUEUE_FULL = "CAD_QUEUE_FULL"
CAD_OPERATION_TIMEOUT = "CAD_OPERATION_TIMEOUT"
CAD_THREAD_AFFINITY = "CAD_THREAD_AFFINITY"
DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
DOCUMENT_STALE = "DOCUMENT_STALE"
DOCUMENT_READ_ONLY = "DOCUMENT_READ_ONLY"
DOCUMENT_CONFLICT = "DOCUMENT_CONFLICT"
DOCUMENT_DIRTY = "DOCUMENT_DIRTY"
DOCUMENT_OWNERSHIP_DENIED = "DOCUMENT_OWNERSHIP_DENIED"
ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
INVALID_GEOMETRY = "INVALID_GEOMETRY"
INVALID_ACTION = "INVALID_ACTION"
UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
PERMISSION_DENIED = "PERMISSION_DENIED"
PATH_DENIED = "PATH_DENIED"
OUTPUT_EXISTS = "OUTPUT_EXISTS"
IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
OPERATION_UNCERTAIN = "OPERATION_UNCERTAIN"
LEASE_REQUIRED = "LEASE_REQUIRED"
LEASE_CONFLICT = "LEASE_CONFLICT"
SAVE_FAILED = "SAVE_FAILED"
SCREENSHOT_UNAVAILABLE = "SCREENSHOT_UNAVAILABLE"
SCREENSHOT_FAILED = "SCREENSHOT_FAILED"
SCREENSHOT_BLANK = "SCREENSHOT_BLANK"
PARTIAL_COMMIT = "PARTIAL_COMMIT"
RUN_NOT_FOUND = "RUN_NOT_FOUND"
RUN_STATE_INVALID = "RUN_STATE_INVALID"
VALIDATION_FAILED = "VALIDATION_FAILED"
INTERNAL_ERROR = "INTERNAL_ERROR"

_RETRYABLE = {
    CAD_QUEUE_FULL,
    CAD_OPERATION_TIMEOUT,
    CAD_NOT_RESPONDING,
    DOCUMENT_CONFLICT,
}

# Protocol-level JSON-RPC error code for state failures.
_PROTOCOL_ERROR_CODE = -32000


class GstarCadMcpError(Exception):
    """Base class for server domain errors."""


class ExpectedCadError(GstarCadMcpError):
    """Expected, model- or operator-correctable failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool | None = None,
        context: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable if retryable is not None else code in _RETRYABLE
        self.context = context or {}

    def client_message(self) -> str:
        return f"{self.code}: {sanitize_message(self.message)}"


class CadUnavailableError(ExpectedCadError):
    pass


class DocumentConflictError(ExpectedCadError):
    pass


class EntityNotFoundError(ExpectedCadError):
    pass


class PathDeniedError(ExpectedCadError):
    pass


class PartialCommitError(ExpectedCadError):
    pass


def sanitize_message(text: str) -> str:
    """Strip absolute paths and reprs from client-visible text."""
    import re

    text = re.sub(r"[A-Za-z]:\\[^\s\"']+", "<path>", text)
    text = re.sub(r"<[^<>]*object at 0x[0-9A-Fa-f]+[^<>]*>", "<object>", text)
    return text


def to_tool_error(exc: ExpectedCadError) -> ToolError:
    return ToolError(exc.client_message())


def to_protocol_error(exc: ExpectedCadError) -> MCPError:
    return MCPError(_PROTOCOL_ERROR_CODE, exc.client_message())
