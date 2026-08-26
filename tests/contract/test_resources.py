"""MCP resource contract tests (guideline §18, §31.7)."""

from __future__ import annotations

import base64
import json
import uuid

import pytest
from support.flows import apply_batch, call, content, document_id_of, new_document
from support.struct import assert_no_absolute_paths, deep_find

pytestmark = pytest.mark.anyio


def _first_content(read_result):
    contents = getattr(read_result, "contents", None) or read_result
    return contents[0]


class TestResourceCatalog:
    async def test_status_resource_readable(self, client):
        read = await client.read_resource("gcad://status")
        item = _first_content(read)
        payload = json.loads(item.text)
        assert deep_find(payload, "runtime_state") == "ready"

    async def test_documents_resource_readable(self, client):
        await new_document(client)
        read = await client.read_resource("gcad://documents")
        item = _first_content(read)
        payload = json.loads(item.text)
        assert deep_find(payload, "documents") is not None

    async def test_resource_templates_declared(self, client):
        templates = await client.list_resource_templates()
        uris = [t.uri_template for t in templates.resource_templates]
        assert any("runs" in uri for uri in uris), f"run resource templates missing: {uris!r}"

    async def test_missing_resource_raises_protocol_error(self, client):
        run_id = uuid.uuid4()
        with pytest.raises(Exception) as excinfo:
            await client.read_resource(f"gcad://runs/{run_id}/manifest")
        message = str(excinfo.value)
        assert (
            "not found" in message.lower() or "ResourceNotFound" in message
        ), f"missing resource must raise ResourceNotFoundError, got: {message!r}"
        assert "Traceback" not in message

    async def test_invalid_uuid_in_template_rejected(self, client):
        with pytest.raises(Exception):
            await client.read_resource("gcad://runs/not-a-uuid/manifest")


class TestScreenshotResource:
    async def test_png_resource_readable_and_binary_safe(self, client):
        created = await new_document(client)
        document_id = document_id_of(created)
        batch = await apply_batch(client, document_id, expected_revision=0)
        assert not batch.is_error

        capture = await call(
            client,
            "gcad_capture_view",
            {
                "operation_id": str(uuid.uuid4()),
                "document_id": document_id,
                "name": "review",
            },
        )
        assert not capture.is_error, f"capture_view failed: {capture!r}"
        uri = str(deep_find(content(capture), "resource_uri"))

        read = await client.read_resource(uri)
        item = _first_content(read)
        blob = getattr(item, "blob", None)
        assert blob, "PNG resource must be delivered as binary content"
        data = base64.b64decode(blob)
        assert data.startswith(b"\x89PNG\r\n\x1a\n"), "PNG magic bytes missing"
        mime = getattr(item, "mimeType", None) or getattr(item, "mime_type", None)
        assert mime == "image/png"

    async def test_missing_snapshot_resource_not_found(self, client):
        created = await new_document(client)
        document_id = document_id_of(created)
        run = await call(
            client,
            "gcad_begin_run",
            {
                "operation_id": str(uuid.uuid4()),
                "document_id": document_id,
                "title": "t",
                "intent": "i",
                "units": "millimeters",
            },
        )
        assert not run.is_error
        run_id = deep_find(content(run), "run_id")
        with pytest.raises(Exception):
            await client.read_resource(f"gcad://runs/{run_id}/snapshots/never-captured")


class TestResourceHygiene:
    async def test_resources_do_not_leak_absolute_paths(self, client):
        created = await new_document(client)
        document_id = document_id_of(created)
        uris = [
            "gcad://status",
            "gcad://documents",
            f"gcad://documents/{document_id}/summary",
            f"gcad://documents/{document_id}/layers",
            f"gcad://documents/{document_id}/layouts",
        ]
        for uri in uris:
            try:
                read = await client.read_resource(uri)
            except Exception:
                continue  # optional resource shapes; absence covered elsewhere
            item = _first_content(read)
            text = getattr(item, "text", None)
            if text:
                assert_no_absolute_paths(json.loads(text))
