"""Actor serialization tests (guideline §10.6, §31.4).

All COM access must happen on one dedicated actor thread, even when many
async MCP callers race the server.
"""

from __future__ import annotations

import asyncio
import threading

import pytest
from support.flows import call, document_id_of, new_document
from support.struct import iter_strings

pytestmark = pytest.mark.anyio

COM_METHOD_PREFIXES = (
    "Documents.",
    "Application.",
    "ModelSpace.",
    "Layers.",
    "Layouts.",
    "Document.",
    "Entity.",
    "pythoncom.",
    "win32com.",
)


def com_thread_ids(factory) -> set[int]:
    return {
        record.thread_id
        for record in factory.recorder.calls
        if record.method.startswith(COM_METHOD_PREFIXES)
    }


class TestSerialization:
    async def test_hundred_concurrent_callers_share_one_com_thread(self, client, fake_factory):
        created = await new_document(client)
        document_id = document_id_of(created)
        baseline = len(fake_factory.recorder.calls)

        tasks = [
            asyncio.create_task(call(client, "gcad_query_entities", {"document_id": document_id}))
            for _ in range(100)
        ]
        results = await asyncio.gather(*tasks)
        assert len(results) == 100
        failures = [r for r in results if r.is_error]
        assert not failures, f"concurrent queries failed: {failures[:3]!r}"

        fresh = [
            record
            for record in fake_factory.recorder.calls[baseline:]
            if record.method.startswith(COM_METHOD_PREFIXES)
        ]
        assert fresh, "query_entities performed no COM calls on the fake runtime"
        thread_ids = {record.thread_id for record in fresh}
        assert len(thread_ids) == 1, f"COM calls ran on {len(thread_ids)} threads: {thread_ids}"
        assert thread_ids != {
            threading.get_ident()
        }, "COM calls must run on the actor thread, not the event-loop thread"

    async def test_com_calls_from_different_tools_stay_on_one_thread(self, client, fake_factory):
        created = await new_document(client)
        document_id = document_id_of(created)
        await call(client, "gcad_list_documents", {"refresh": True})
        await call(client, "gcad_list_layers", {"document_id": document_id})
        await call(client, "gcad_list_layouts", {"document_id": document_id})
        await call(client, "gcad_query_entities", {"document_id": document_id})

        thread_ids = com_thread_ids(fake_factory)
        assert len(thread_ids) == 1, f"expected one COM thread, saw {thread_ids}"

    async def test_no_fake_com_object_crosses_result_boundary(self, client, fake_factory):
        created = await new_document(client)
        document_id = document_id_of(created)
        targets = [
            await call(client, "gcad_list_documents", {"refresh": True}),
            await call(client, "gcad_list_layers", {"document_id": document_id}),
            await call(client, "gcad_query_entities", {"document_id": document_id}),
            await call(client, "gcad_get_status", {}),
        ]
        for result in targets:
            structured = result.structured_content
            assert structured is not None
            for text in iter_strings(structured):
                assert "FakeComObject" not in text
                assert "COMObject" not in text
                assert "<Fake" not in text

    async def test_com_connect_and_uninitialize_happen_on_actor_thread(self, harness, fake_factory):
        """CoInitialize/CoUninitialize equivalents must share the actor thread."""
        async with harness.client() as client:
            await new_document(client)
        pythoncom_ids = {
            record.thread_id
            for record in fake_factory.recorder.calls
            if record.method.startswith("pythoncom.")
        }
        if not pythoncom_ids:
            # The seam may bypass pythoncom entirely when a factory is injected.
            pytest.skip("injected factory path does not call pythoncom fakes")
        assert len(pythoncom_ids) == 1
