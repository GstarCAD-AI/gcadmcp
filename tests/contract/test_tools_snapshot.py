"""tools/list contract snapshot (guideline §31.7).

The public schema surface is snapshot-tested: names, titles, descriptions,
input/output schemas, and annotations.  The snapshot is created on first run
and compared on every later run; unintended changes are breaking changes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from support.flows import EXPECTED_TOOL_NAMES

pytestmark = pytest.mark.anyio

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "snapshots" / "tools.json"


def _serialize_tool(tool) -> dict:
    annotations = getattr(tool, "annotations", None)
    serialized_annotations = None
    if annotations is not None:
        serialized_annotations = {
            key: getattr(annotations, key, None)
            for key in (
                "read_only_hint",
                "idempotent_hint",
                "destructive_hint",
                "open_world_hint",
                "title",
            )
        }
    return {
        "name": tool.name,
        "title": getattr(tool, "title", None),
        "description": getattr(tool, "description", None),
        "inputSchema": getattr(tool, "inputSchema", None),
        "outputSchema": getattr(tool, "outputSchema", None),
        "annotations": serialized_annotations,
    }


def _snapshot(tools) -> dict:
    return {tool.name: _serialize_tool(tool) for tool in sorted(tools, key=lambda t: t.name)}


class TestToolsListSnapshot:
    async def test_exact_tool_names(self, client):
        result = await client.list_tools()
        names = {tool.name for tool in result.tools}
        missing = EXPECTED_TOOL_NAMES - names
        extra = names - EXPECTED_TOOL_NAMES
        assert not missing, f"missing tools: {sorted(missing)}"
        assert not extra, f"unexpected extra tools: {sorted(extra)}"

    async def test_snapshot_matches(self, client):
        result = await client.list_tools()
        current = _snapshot(result.tools)
        if not SNAPSHOT_PATH.exists():
            SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
            SNAPSHOT_PATH.write_text(
                json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            pytest.skip("snapshot created on first run; compare on next run")
        expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        assert current == expected, (
            "tools/list snapshot changed. Review the diff; if intentional, "
            f"delete {SNAPSHOT_PATH} and rerun to regenerate."
        )

    async def test_annotations_are_closed_world(self, client):
        result = await client.list_tools()
        for tool in result.tools:
            annotations = getattr(tool, "annotations", None)
            assert annotations is not None, f"{tool.name} lacks ToolAnnotations (§16)"
            assert (
                getattr(annotations, "open_world_hint", False) is False
            ), f"{tool.name} must be closed-world (§16)"

    async def test_read_only_tools_annotated_read_only(self, client):
        read_only = {
            "gcad_get_status",
            "gcad_list_documents",
            "gcad_list_layers",
            "gcad_list_layouts",
            "gcad_query_entities",
            "gcad_get_entities",
            "gcad_get_run_status",
        }
        result = await client.list_tools()
        for tool in result.tools:
            if tool.name in read_only:
                assert (
                    getattr(tool.annotations, "read_only_hint", False) is True
                ), f"{tool.name} must carry read_only_hint=True"
