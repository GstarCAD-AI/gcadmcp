"""Config mutation helpers and domain-error constructors for tests."""

from __future__ import annotations

import importlib
from typing import Any


def with_overrides(config: Any, section: str, **fields: Any) -> Any:
    """Return ``config`` with ``config.<section>`` fields overridden.

    Falls back to in-place attribute assignment when pydantic copying is not
    available on the section model.
    """
    target = getattr(config, section, None)
    if target is not None and hasattr(target, "model_copy"):
        try:
            updated_section = target.model_copy(update=fields)
            return config.model_copy(update={section: updated_section})
        except Exception:  # noqa: BLE001 - fall through to setattr path
            pass
    if target is not None:
        for key, value in fields.items():
            try:
                setattr(target, key, value)
            except Exception:  # noqa: BLE001
                pass
    return config


def make_expected_cad_error(message: str, *, code: str = "CAD_CONNECTION_FAILED") -> Exception:
    """Construct an ``ExpectedCadError`` (or close relative) for injection."""
    errors = importlib.import_module("gstarcad_mcp.errors")
    candidates = []
    for name in ("CadUnavailableError", "ExpectedCadError"):
        cls = getattr(errors, name, None)
        if isinstance(cls, type) and issubclass(cls, Exception):
            candidates.append(cls)
    for cls in candidates:
        for construct in (
            lambda: cls(message),
            lambda: cls(message=message),
            lambda: cls(code=code, message=message),
            lambda: cls(code, message),
        ):
            try:
                return construct()
            except TypeError:
                continue
    return RuntimeError(message)
