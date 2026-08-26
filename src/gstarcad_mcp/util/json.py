"""Deterministic JSON helpers and wire-safety checks."""

from __future__ import annotations

import hashlib
import json
from typing import Any

_WIRE_TYPES = (str, int, float, bool, type(None), list, dict)


def canonical_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def request_hash(value: Any) -> str:
    return hashlib.sha256(canonical_dumps(value).encode("utf-8")).hexdigest()


def assert_wire_safe(value: Any, *, path: str = "$") -> Any:
    """Recursively verify a value contains only JSON-wire types.

    Rejects COM objects, wrappers, file handles, callables, and anything else
    that must not cross the actor thread boundary.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"Non-string dict key at {path}")
            assert_wire_safe(item, path=f"{path}.{key}")
        return value
    if isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            assert_wire_safe(item, path=f"{path}[{i}]")
        return value
    if isinstance(value, _WIRE_TYPES):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            raise TypeError(f"Non-finite float at {path}")
        return value
    raise TypeError(f"Non-wire-safe value at {path}: {type(value).__name__}")
