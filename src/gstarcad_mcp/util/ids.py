"""Identifier helpers and slug validation."""

from __future__ import annotations

import re
from uuid import UUID, uuid4

_SLUG_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def new_uuid() -> UUID:
    return uuid4()


def parse_uuid(value: str, *, what: str = "identifier") -> UUID:
    try:
        return UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        from gstarcad_mcp.errors import INVALID_ACTION, ExpectedCadError

        raise ExpectedCadError(INVALID_ACTION, f"Invalid {what}: not a UUID") from exc


def validate_slug(value: str, *, what: str = "name") -> str:
    if not _SLUG_RE.match(value or ""):
        from gstarcad_mcp.errors import INVALID_ACTION, ExpectedCadError

        raise ExpectedCadError(INVALID_ACTION, f"Invalid {what}: must match [A-Za-z0-9_-]{{1,64}}")
    return value
