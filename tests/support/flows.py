"""Shared flows for MCP contract tests (guideline §16, §31.7, §36)."""

from __future__ import annotations

import uuid
from typing import Any

from support.harness import error_code_value
from support.struct import deep_find

# The canonical example batch from guideline §36.2.
EXAMPLE_BATCH_ACTIONS = [
    {
        "op": "ensure_layer",
        "action_id": "layer-outline",
        "name": "A-OUTLINE",
        "color": 7,
    },
    {
        "op": "create_rect",
        "action_id": "main-outline",
        "corner1": {"x": 0, "y": 0, "z": 0},
        "corner2": {"x": 80, "y": 50, "z": 0},
        "layer": "A-OUTLINE",
        "color": 7,
        "lineweight": 30,
    },
    {
        "op": "create_circle",
        "action_id": "hole-1",
        "center": {"x": 20, "y": 25, "z": 0},
        "radius": 3,
        "layer": "A-OUTLINE",
    },
    {
        "op": "create_circle",
        "action_id": "hole-2",
        "center": {"x": 60, "y": 25, "z": 0},
        "radius": 3,
        "layer": "A-OUTLINE",
    },
    {
        "op": "zoom_extents",
        "action_id": "zoom",
    },
]

EXPECTED_TOOL_NAMES = frozenset(
    {
        "gcad_get_status",
        "gcad_list_documents",
        "gcad_new_document",
        "gcad_open_document",
        "gcad_activate_document",
        "gcad_save_document",
        "gcad_close_document",
        "gcad_list_layers",
        "gcad_list_layouts",
        "gcad_query_entities",
        "gcad_get_entities",
        "gcad_ensure_layers",
        "gcad_create_entities",
        "gcad_apply_actions",
        "gcad_capture_view",
        "gcad_begin_run",
        "gcad_capture_before_state",
        "gcad_collect_evidence",
        "gcad_validate_run",
        "gcad_finalize_run",
        "gcad_get_run_status",
    }
)

EXPECTED_PROMPT_NAMES = frozenset(
    {
        "gcad_create_2d_drawing",
        "gcad_modify_existing_drawing",
        "gcad_mechanical_three_view",
        "gcad_review_and_repair",
        "gcad_finalize_with_evidence",
        "gcad_validate_before_delivery",
    }
)


async def call(client: Any, name: str, arguments: dict) -> Any:
    return await client.call_tool(name, arguments)


def content(result: Any) -> dict:
    structured = getattr(result, "structured_content", None)
    assert structured is not None, f"tool result has no structured content: {result!r}"
    return structured


async def new_document(client: Any) -> dict:
    result = await call(
        client,
        "gcad_new_document",
        {"operation_id": str(uuid.uuid4()), "activate": True},
    )
    assert not result.is_error, f"gcad_new_document failed: {result!r}"
    return content(result)


def document_id_of(payload: dict) -> str:
    document_id = deep_find(payload, "document_id")
    assert document_id, f"no document_id in new-document result: {payload!r}"
    return str(document_id)


def revision_of(payload: dict, key: str = "revision_after") -> int | None:
    value = deep_find(payload, key)
    if value is None and key == "revision_after":
        value = deep_find(payload, "revision")
    return None if value is None else int(value)


async def apply_batch(
    client: Any,
    document_id: str,
    *,
    expected_revision: int | None = 0,
    actions: list[dict] | None = None,
    run_id: str | None = None,
) -> Any:
    arguments: dict[str, Any] = {
        "operation_id": str(uuid.uuid4()),
        "document_id": document_id,
        "expected_revision": expected_revision,
        "atomic": True,
        "stop_on_error": True,
        "actions": actions if actions is not None else EXAMPLE_BATCH_ACTIONS,
    }
    if run_id is not None:
        arguments["run_id"] = run_id
    return await call(client, "gcad_apply_actions", arguments)


def error_text(result: Any) -> str:
    texts: list[str] = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            texts.append(text)
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        texts.append(str(structured))
    return "\n".join(texts)


def assert_tool_error(result: Any, code: str) -> None:
    assert result.is_error, f"expected an error result, got success: {result!r}"
    expected = error_code_value(code)
    text = error_text(result)
    assert (
        expected in text or code in text
    ), f"expected error code {code} in client-visible error, got: {text!r}"
