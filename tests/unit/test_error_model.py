"""Error model tests (§24, §31.1): codes, hierarchy, client-message sanitization."""

from __future__ import annotations

import pytest
from support.harness import error_code_value

import gstarcad_mcp.errors as errors_mod
from gstarcad_mcp.errors import (
    ExpectedCadError,
    GstarCadMcpError,
    PathDeniedError,
    sanitize_message,
)

REQUIRED_CODES = [
    "PLATFORM_UNSUPPORTED",
    "GSTARCAD_NOT_INSTALLED",
    "CAD_CONNECTION_FAILED",
    "CAD_DISCONNECTED",
    "CAD_QUEUE_FULL",
    "CAD_OPERATION_TIMEOUT",
    "DOCUMENT_NOT_FOUND",
    "DOCUMENT_CONFLICT",
    "DOCUMENT_DIRTY",
    "ENTITY_NOT_FOUND",
    "INVALID_ACTION",
    "UNSUPPORTED_OPERATION",
    "PERMISSION_DENIED",
    "PATH_DENIED",
    "OUTPUT_EXISTS",
    "IDEMPOTENCY_CONFLICT",
    "OPERATION_UNCERTAIN",
    "SAVE_FAILED",
    "SCREENSHOT_FAILED",
    "RUN_NOT_FOUND",
    "INTERNAL_ERROR",
]


@pytest.mark.parametrize("name", REQUIRED_CODES)
def test_required_error_code_constant_exists(name: str) -> None:
    value = error_code_value(name)
    assert value == name, f"error code {name} must be the stable string {name!r}, got {value!r}"


def test_codes_are_unique_strings() -> None:
    values = [error_code_value(name) for name in REQUIRED_CODES]
    assert len(set(values)) == len(values)


class TestHierarchy:
    def test_expected_error_is_domain_error(self):
        assert issubclass(ExpectedCadError, GstarCadMcpError)

    def test_specialized_errors_exist(self):
        assert issubclass(PathDeniedError, ExpectedCadError)
        assert issubclass(errors_mod.DocumentConflictError, ExpectedCadError)

    def test_retryability_defaults(self):
        assert ExpectedCadError("CAD_QUEUE_FULL", "full").retryable is True
        assert ExpectedCadError("DOCUMENT_CONFLICT", "conflict").retryable is True
        assert ExpectedCadError("PATH_DENIED", "denied").retryable is False
        # explicit override wins
        assert ExpectedCadError("PATH_DENIED", "denied", retryable=True).retryable is True


class TestClientMessages:
    def test_client_message_prefixed_with_code(self):
        exc = ExpectedCadError("DOCUMENT_CONFLICT", "expected revision 0, actual 3")
        assert exc.client_message() == "DOCUMENT_CONFLICT: expected revision 0, actual 3"

    def test_client_message_never_contains_traceback(self):
        exc = ExpectedCadError("INTERNAL_ERROR", "Traceback (most recent call last): nope")
        # The sanitized client message must not include a stack trace marker.
        message = exc.client_message()
        assert message.startswith("INTERNAL_ERROR:")

    def test_absolute_windows_paths_are_stripped(self):
        text = sanitize_message("Failed to open C:\\Users\\bob\\Documents\\plan.dwg today")
        assert "C:\\" not in text
        assert "Users" not in text
        assert "<path>" in text

    def test_object_reprs_are_stripped(self):
        text = sanitize_message("bad value <PyIDispatch object at 0x000001F2A3B4C5D6>")
        assert "0x000001F2A3B4C5D6" not in text
        assert "<object>" in text

    def test_client_message_applies_sanitization(self):
        exc = ExpectedCadError("SAVE_FAILED", "Save failed for C:\\temp\\out.dwg")
        assert "C:\\temp" not in exc.client_message()
