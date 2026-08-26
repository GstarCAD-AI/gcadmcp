"""Harness for building the MCP server against the fake CAD runtime.

The public contract is ``create_server(config, *, cad_factory=...)`` (see
``gstarcad_mcp.server``); this module concentrates all wiring in one place so
the tests themselves stay declarative.
"""

from __future__ import annotations

import importlib
import os
from contextlib import asynccontextmanager
from typing import Any

CONFIG_ENV_VARS = {
    "GSTARCAD_MCP_PERMISSION_PROFILE": "authoring",
    "GSTARCAD_MCP_LOG_LEVEL": "INFO",
}


def _import(module_name: str) -> Any:
    return importlib.import_module(module_name)


def make_test_config(workspace_root: Any, *, env: Any | None = None) -> Any:
    """Build a ``ServerConfig`` rooted at ``workspace_root``.

    Uses the documented configuration precedence (§28): environment variables
    override safe defaults.  ``env`` is a pytest ``MonkeyPatch``-like object
    used to set the variables for the duration of the test; without it the
    process environment is modified directly.
    """
    config_mod = _import("gstarcad_mcp.config")
    if env is not None:
        env.setenv("GSTARCAD_MCP_WORKSPACE_ROOT", str(workspace_root))
        for key, value in CONFIG_ENV_VARS.items():
            env.setenv(key, value)
    else:  # pragma: no cover - tests always pass monkeypatch
        os.environ["GSTARCAD_MCP_WORKSPACE_ROOT"] = str(workspace_root)
        for key, value in CONFIG_ENV_VARS.items():
            os.environ[key] = value
    return config_mod.load_config()


def error_code_value(name: str) -> str:
    """Return the string value of an error-code constant from ``errors``."""
    errors = _import("gstarcad_mcp.errors")
    candidate = getattr(errors, name, None)
    if candidate is None:
        raise AssertionError(f"error code constant {name!r} not found in gstarcad_mcp.errors")
    value = getattr(candidate, "value", candidate)
    assert isinstance(value, str), f"error code {name!r} is not a string: {candidate!r}"
    return value


class Harness:
    """Builds the MCP server (or a bare actor) with the fake CAD factory."""

    def __init__(self, config: Any, cad_factory: Any) -> None:
        self.config = config
        self.cad_factory = cad_factory
        self._server_module = _import("gstarcad_mcp.server")

    # -- construction ---------------------------------------------------------
    def build_server(self) -> Any:
        """``create_server(config, cad_factory=fake)``."""
        return self._server_module.create_server(self.config, cad_factory=self.cad_factory)

    def build_actor(self) -> Any:
        """Construct ``CadActor`` directly with the fake factory injected."""
        actor_mod = _import("gstarcad_mcp.runtime.cad_actor")
        dispatcher_mod = _import("gstarcad_mcp.runtime.dispatcher")
        registry_mod = _import("gstarcad_mcp.runtime.document_registry")
        return actor_mod.CadActor(
            self.config.cad,
            dispatcher_mod.CadDispatcher(),
            cad_factory=self.cad_factory,
            registry=registry_mod.DocumentRegistry(),
        )

    # -- client helpers -------------------------------------------------------
    @asynccontextmanager
    async def client(self):
        from mcp import Client

        server = self.build_server()
        async with Client(server, raise_exceptions=True) as value:
            yield value

    def force_cleanup(self) -> None:
        """No module-level seams are used; kept for fixture compatibility."""


def harness_for(config: Any, cad_factory: Any) -> Harness:
    return Harness(config, cad_factory)
