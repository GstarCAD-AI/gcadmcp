"""Discovery helpers for the public pydantic model contract.

The guideline names the request models (``ApplyActionsRequest``,
``EntityQuery``, ...) but not their module; these helpers locate them.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

_MODEL_CACHE: dict[str, Any] = {}
_WALKED = False

_CANDIDATE_MODULES = (
    "gstarcad_mcp.models",
    "gstarcad_mcp.schemas",
    "gstarcad_mcp.actions",
    "gstarcad_mcp.runtime.actions",
    "gstarcad_mcp.runtime.models",
    "gstarcad_mcp.tools.models",
)


def _pydantic_base() -> Any:
    try:
        from pydantic import BaseModel

        return BaseModel
    except Exception:  # pragma: no cover
        return None


def _scan_package() -> None:
    global _WALKED
    if _WALKED:
        return
    _WALKED = True
    base_model = _pydantic_base()
    package = importlib.import_module("gstarcad_mcp")
    for module_info in pkgutil.walk_packages(package.__path__, prefix="gstarcad_mcp."):
        try:
            module = importlib.import_module(module_info.name)
        except Exception:
            continue
        for name in dir(module):
            obj = getattr(module, name)
            if base_model is not None and isinstance(obj, type) and issubclass(obj, base_model):
                _MODEL_CACHE.setdefault(name, obj)


def find_model(name: str) -> Any:
    """Return the pydantic model class called ``name`` from the package."""
    if name in _MODEL_CACHE:
        return _MODEL_CACHE[name]
    for module_name in _CANDIDATE_MODULES:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        obj = getattr(module, name, None)
        if obj is not None:
            _MODEL_CACHE[name] = obj
            return obj
    _scan_package()
    if name not in _MODEL_CACHE:
        raise AssertionError(
            f"model {name!r} not found in gstarcad_mcp; "
            "the guideline requires it as part of the public contract"
        )
    return _MODEL_CACHE[name]


def maybe_model(name: str) -> Any | None:
    try:
        return find_model(name)
    except AssertionError:
        return None
