"""Helpers for inspecting structured MCP results without assuming field paths."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

_DRIVE_PATH = re.compile(r"\b[A-Za-z]:[\\/]")
_UNC_PATH = re.compile(r"\\\\[A-Za-z0-9]")


def deep_find(data: Any, key: str) -> Any | None:
    """Return the first value stored under ``key`` anywhere in ``data``."""
    for found in deep_find_all(data, key):
        return found
    return None


def deep_find_all(data: Any, key: str) -> Iterator[Any]:
    if isinstance(data, dict):
        for item_key, value in data.items():
            if item_key == key:
                yield value
            yield from deep_find_all(value, key)
    elif isinstance(data, list):
        for item in data:
            yield from deep_find_all(item, key)


def iter_strings(data: Any) -> Iterator[str]:
    """Yield every string value reachable in a structured result."""
    if isinstance(data, str):
        yield data
    elif isinstance(data, dict):
        for key, value in data.items():
            yield str(key)
            yield from iter_strings(value)
    elif isinstance(data, list):
        for item in data:
            yield from iter_strings(item)


def assert_no_absolute_paths(data: Any, *, allowed: tuple[str, ...] = ()) -> None:
    """Fail when any string in ``data`` looks like an absolute filesystem path."""
    for text in iter_strings(data):
        if any(marker in text for marker in allowed):
            continue
        if _DRIVE_PATH.search(text):
            raise AssertionError(f"absolute Windows path leaked: {text!r}")
        if _UNC_PATH.search(text):
            raise AssertionError(f"UNC path leaked: {text!r}")
        if text.startswith("/"):
            raise AssertionError(f"absolute path leaked: {text!r}")


def assert_no_stack_traces(data: Any) -> None:
    for text in iter_strings(data):
        assert (
            "Traceback (most recent call last)" not in text
        ), f"stack trace leaked into client-visible output: {text[:200]!r}"
