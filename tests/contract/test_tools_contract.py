"""Tool-result contract tests (guideline §24.3, §31.7).

- every success result is structured;
- expected failures map to ``is_error=True`` with a stable domain code;
- unexpected failures are sanitized (no tracebacks, no absolute paths);
- operation ids give idempotent retry semantics without duplicating entities.
"""

from __future__ import annotations

import uuid

import pytest
from support.flows import (
    assert_tool_error,
    call,
    content,
    document_id_of,
    new_document,
)
from support.struct import assert_no_absolute_paths, assert_no_stack_traces, deep_find

pytestmark = pytest.mark.anyio


class TestStructuredResults:
    async def test_success_results_are_structured(self, client):
        created = await new_document(client)
        document_id = document_id_of(created)
        results = [
            await call(client, "gcad_get_status", {}),
            await call(client, "gcad_list_documents", {"refresh": True}),
            await call(client, "gcad_list_layers", {"document_id": document_id}),
            await call(client, "gcad_list_layouts", {"document_id": document_id}),
            await call(client, "gcad_query_entities", {"document_id": document_id}),
        ]
        for result in results:
            assert not result.is_error
            assert result.structured_content is not None, f"structured_content missing: {result!r}"

    async def test_status_reports_ready_with_fake_runtime(self, client):
        result = await call(client, "gcad_get_status", {})
        assert not result.is_error
        payload = content(result)
        assert deep_find(payload, "runtime_state") == "ready"
        assert deep_find(payload, "connected") is True
        assert deep_find(payload, "runtime_id"), "status must expose runtime_id"

    async def test_unknown_fields_rejected_at_protocol_boundary(self, client):
        try:
            result = await call(client, "gcad_get_status", {"bogus_field": True})
        except Exception:
            return  # protocol-level rejection is acceptable
        assert result.is_error, "unknown input fields must not be silently accepted"


class TestToolErrors:
    async def test_unknown_document_is_tool_error(self, client):
        result = await call(
            client,
            "gcad_activate_document",
            {"document_id": str(uuid.uuid4())},
        )
        assert_tool_error(result, "DOCUMENT_NOT_FOUND")
        assert_no_stack_traces(result.content)

    async def test_path_denied_for_hostile_open_path(self, client):
        result = await call(
            client,
            "gcad_open_document",
            {
                "operation_id": str(uuid.uuid4()),
                "path": "..\\..\\Windows\\System32\\evil.dwg",
            },
        )
        assert result.is_error
        text = "\n".join(item.text for item in result.content if getattr(item, "text", None))
        assert "PATH_DENIED" in text
        assert_no_absolute_paths(text)
        assert_no_stack_traces(text)

    async def test_error_messages_are_sanitized(self, client):
        hostile = [
            (
                "gcad_open_document",
                {"operation_id": str(uuid.uuid4()), "path": "C:\\outside\\x.dwg"},
            ),
            ("gcad_activate_document", {"document_id": str(uuid.uuid4())}),
        ]
        for name, args in hostile:
            result = await call(client, name, args)
            assert result.is_error
            for item in result.content:
                text = getattr(item, "text", "") or ""
                assert "Traceback" not in text
                assert_no_absolute_paths(text)


class TestToolLevelIdempotency:
    async def test_same_operation_same_request_returns_same_document(self, client):
        operation_id = str(uuid.uuid4())
        args = {"operation_id": operation_id, "activate": True}
        first = await call(client, "gcad_new_document", args)
        second = await call(client, "gcad_new_document", args)
        assert not first.is_error and not second.is_error
        assert document_id_of(content(first)) == document_id_of(
            content(second)
        ), "retrying with the same operation_id must return the stored result"

        listing = await call(client, "gcad_list_documents", {"refresh": True})
        occurrences = str(content(listing)).count(document_id_of(content(first)))
        assert occurrences >= 1
        documents = deep_find(content(listing), "documents") or []
        assert len(documents) == 1, f"retry duplicated the document: {documents!r}"

    async def test_same_operation_different_request_conflicts(self, client):
        operation_id = str(uuid.uuid4())
        first = await call(
            client, "gcad_new_document", {"operation_id": operation_id, "activate": True}
        )
        assert not first.is_error
        conflicting = await call(
            client, "gcad_new_document", {"operation_id": operation_id, "activate": False}
        )
        assert_tool_error(conflicting, "IDEMPOTENCY_CONFLICT")

    async def test_retry_after_timeout_does_not_duplicate_entities(self, client):
        created = await new_document(client)
        document_id = document_id_of(created)

        actions = [
            {
                "op": "create_circle",
                "action_id": "only-circle",
                "center": {"x": 5, "y": 5, "z": 0},
                "radius": 2,
                "layer": "0",
            }
        ]
        operation_id = str(uuid.uuid4())
        first = await call(
            client,
            "gcad_apply_actions",
            {
                "operation_id": operation_id,
                "document_id": document_id,
                "expected_revision": 0,
                "atomic": True,
                "stop_on_error": True,
                "actions": actions,
            },
        )
        assert not first.is_error, f"first apply failed: {first!r}"

        # The "retry" after a lost response: identical operation and payload.
        retry = await call(
            client,
            "gcad_apply_actions",
            {
                "operation_id": operation_id,
                "document_id": document_id,
                "expected_revision": 0,
                "atomic": True,
                "stop_on_error": True,
                "actions": actions,
            },
        )
        assert not retry.is_error, f"idempotent retry failed: {retry!r}"

        entities = await call(client, "gcad_query_entities", {"document_id": document_id})
        payload = content(entities)
        found = deep_find(payload, "entities") or []
        circles = [e for e in found if "circle" in str(e).lower() or "Circle" in str(e)]
        assert len(circles) == 1, f"retry duplicated the created entity: {found!r}"

    async def test_read_only_tools_need_no_operation_id(self, client):
        for name, args in (
            ("gcad_get_status", {}),
            ("gcad_list_documents", {}),
        ):
            result = await call(client, name, args)
            assert not result.is_error, f"{name} must not require an operation id"
