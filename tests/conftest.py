"""Shared pytest fixtures for the gstarcad-mcp-server test suite.

The suite targets the public contract of ``gstarcad_mcp``:

- ``gstarcad_mcp.server.create_server`` (with the ``cad_factory`` seam)
- ``gstarcad_mcp.config.load_config`` / ``ServerConfig``
- ``gstarcad_mcp.errors`` error-code constants
- ``gstarcad_mcp.policy.workspace.WorkspacePolicy``
- ``gstarcad_mcp.policy.idempotency.IdempotencyStore``
- ``gstarcad_mcp.runtime.cad_actor.CadActor``
- ``gstarcad_mcp.runs.store.RunStore``

All CAD interaction is faked; no real GstarCAD is required.  The OS-level
screenshot capture in ``pygcadwin.view`` is stubbed with a deterministic
synthetic frame so the real Snapshot/PNG-encode path still runs.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

TESTS_ROOT = Path(__file__).resolve().parent
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))

from fakes import FakeCadFactory  # noqa: E402
from support.harness import Harness, harness_for, make_test_config  # noqa: E402

SNAPSHOT_WIDTH = 400
SNAPSHOT_HEIGHT = 300


def _synthetic_rgba(width: int, height: int) -> bytes:
    """Deterministic, non-uniform RGBA frame."""
    row = bytes(range(256)) * (width * 4 // 256 + 1)
    row = row[: width * 4]
    return row * height


@pytest.fixture(autouse=True)
def stub_screen_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace only the OS-level pixel capture in ``pygcadwin.view``.

    Keeps the real ``View.snapshot`` logic (zoom-extents, retry, uniformity
    check, Snapshot construction, PNG encoding) while avoiding any win32
    desktop dependency.
    """
    from pygcadwin import view as view_mod

    rgba = _synthetic_rgba(SNAPSHOT_WIDTH, SNAPSHOT_HEIGHT)

    monkeypatch.setattr(view_mod, "_prepare_hwnd_for_capture", lambda hwnd: None)
    monkeypatch.setattr(
        view_mod,
        "_capture_hwnd_rgba",
        lambda hwnd: (rgba, SNAPSHOT_WIDTH, SNAPSHOT_HEIGHT),
    )


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    for sub in ("inputs", "outputs", "runs", "cache", "state", "logs"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def server_config(workspace_root: Path, monkeypatch: pytest.MonkeyPatch):
    """Return a ``ServerConfig`` rooted in a temporary workspace."""
    return make_test_config(workspace_root, env=monkeypatch)


@pytest.fixture
def fake_factory() -> FakeCadFactory:
    return FakeCadFactory()


@pytest.fixture
def harness(server_config, fake_factory) -> Harness:
    """Synchronous harness: server created with the fake CAD factory."""
    h = harness_for(server_config, fake_factory)
    yield h
    h.force_cleanup()


@pytest_asyncio.fixture
async def client(harness: Harness):
    """In-memory MCP client over a server backed by the fake CAD runtime."""
    async with harness.client() as value:
        yield value


@pytest.fixture
def new_uuid() -> uuid.UUID:
    return uuid.uuid4()
