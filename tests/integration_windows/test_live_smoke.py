"""Real GstarCAD integration tests (guideline §31.8).

These run only on a controlled, interactive Windows machine with a supported
GstarCAD installation, and only when explicitly enabled:

    $env:GSTARCAD_MCP_INTEGRATION = "1"
    uv run pytest tests/integration_windows -q

Run them serially; never run multiple workers against one desktop GstarCAD.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("GSTARCAD_MCP_INTEGRATION") != "1",
    reason="live GstarCAD integration; set GSTARCAD_MCP_INTEGRATION=1 to enable",
)


@pytest.fixture
async def live_client(tmp_path: Path) -> AsyncIterator[tuple]:
    """In-memory client over a server using the REAL CAD runtime."""
    from mcp import Client

    from gstarcad_mcp.config import ServerConfig, WorkspaceSection
    from gstarcad_mcp.server import create_server

    root = tmp_path / "workspace"
    config = ServerConfig(workspace=WorkspaceSection(root=str(root)))
    server = create_server(config)
    async with Client(server, raise_exceptions=True) as client:
        yield client, root


async def _call(client, tool: str, **arguments) -> dict:
    result = await client.call_tool(tool, arguments)
    assert not result.is_error, f"{tool} failed: {result.content}"
    return result.structured_content


async def test_minimum_scenario(live_client):
    """§31.8 minimum scenario: attach, create, draw, query, capture, save,
    close, reopen, verify persistence."""
    client, root = live_client

    status = await _call(client, "gcad_get_status")
    assert "Windows" in status["platform"] or status["platform"] == "win32"
    assert status["runtime_state"] == "ready", status

    created = await _call(client, "gcad_new_document", operation_id=uuid.uuid4())
    document_id = created["document"]["document_id"]

    batch = await _call(
        client,
        "gcad_apply_actions",
        operation_id=uuid.uuid4(),
        document_id=document_id,
        actions=[
            {"op": "ensure_layer", "name": "SMOKE", "color": 3},
            {
                "op": "create_circle",
                "center": [0.0, 0.0, 0.0],
                "radius": 25.0,
                "layer": "SMOKE",
            },
        ],
    )
    assert batch["status"] == "succeeded", batch

    page = await _call(client, "gcad_query_entities", document_id=document_id)
    assert len(page["entities"]) >= 1, page

    shot = await _call(
        client,
        "gcad_capture_view",
        operation_id=uuid.uuid4(),
        document_id=document_id,
        name="review",
    )
    assert shot["byte_size"] > 0
    assert shot["uniform"] is False

    await _call(
        client,
        "gcad_save_document",
        operation_id=uuid.uuid4(),
        document_id=document_id,
        mode="save_as",
        output_relative_path="outputs/it_smoke.dwg",
    )
    assert (root / "outputs" / "it_smoke.dwg").exists(), "DWG was not written"

    await _call(
        client,
        "gcad_close_document",
        operation_id=uuid.uuid4(),
        document_id=document_id,
        save_policy="reject_dirty",
    )

    reopened = await _call(
        client,
        "gcad_open_document",
        operation_id=uuid.uuid4(),
        path="outputs/it_smoke.dwg",
    )
    reopened_id = reopened["document"]["document_id"]
    page2 = await _call(client, "gcad_query_entities", document_id=reopened_id)
    assert len(page2["entities"]) >= 1, "drawn entity did not persist"

    await _call(
        client,
        "gcad_close_document",
        operation_id=uuid.uuid4(),
        document_id=reopened_id,
        save_policy="reject_dirty",
    )
