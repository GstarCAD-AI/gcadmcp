"""Actor lifecycle tests: startup failure, shutdown, registry refresh."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fakes import FakeCadFactory
from support.configutil import make_expected_cad_error
from support.flows import call, content, document_id_of, new_document
from support.harness import harness_for

pytestmark = pytest.mark.anyio


def _make_command() -> object:
    """Build a minimal CadCommand (§10.2) for direct actor execution."""
    import importlib

    module = importlib.import_module("gstarcad_mcp.runtime.command")
    cls = module.CadCommand
    kwargs = {
        "command_id": uuid.uuid4(),
        "name": "status",
        "payload": {},
        "document_id": None,
        "expected_revision": None,
        "run_id": None,
        "deadline_monotonic": None,
    }
    try:
        return cls(**kwargs)
    except TypeError:
        import inspect

        signature = inspect.signature(cls)
        subset = {k: v for k, v in kwargs.items() if k in signature.parameters}
        return cls(**subset)


class TestStartupFailure:
    async def test_startup_exception_propagates_from_actor(self, server_config):
        failure = make_expected_cad_error("GstarCAD failed to start in test")
        factory = FakeCadFactory(startup_error=failure)
        harness = harness_for(server_config, factory)
        actor = harness.build_actor()
        with pytest.raises(Exception) as excinfo:
            await asyncio.wait_for(actor.start(), timeout=15)
        assert "GstarCAD failed to start in test" in str(excinfo.value) or str(
            getattr(excinfo.value, "__cause__", "")
        ), f"startup error not propagated: {excinfo.value!r}"
        await _drain_actor_close(actor)

    async def test_startup_failure_leaves_no_zombie_thread(self, server_config):
        import threading

        failure = make_expected_cad_error("startup denied")
        factory = FakeCadFactory(startup_error=failure)
        harness = harness_for(server_config, factory)
        actor = harness.build_actor()
        before = {t for t in threading.enumerate() if "gstarcad" in t.name.lower()}
        with pytest.raises(Exception):
            await asyncio.wait_for(actor.start(), timeout=15)
        await _drain_actor_close(actor)
        await asyncio.sleep(0.2)
        after = {t for t in threading.enumerate() if "gstarcad" in t.name.lower() and t.is_alive()}
        assert after <= before, f"zombie actor threads remain: {after - before}"


class TestShutdown:
    async def test_shutdown_rejects_new_work(self, server_config, fake_factory):
        harness = harness_for(server_config, fake_factory)
        actor = harness.build_actor()
        await asyncio.wait_for(actor.start(), timeout=15)
        await _drain_actor_close(actor)

        with pytest.raises(Exception):
            await asyncio.wait_for(actor.execute(_make_command()), timeout=10)

    async def test_shutdown_releases_actor_thread(self, server_config, fake_factory):
        import threading

        harness = harness_for(server_config, fake_factory)
        actor = harness.build_actor()
        await asyncio.wait_for(actor.start(), timeout=15)
        await _drain_actor_close(actor)
        await asyncio.sleep(0.2)
        leftover = [
            t for t in threading.enumerate() if "gstarcad" in t.name.lower() and t.is_alive()
        ]
        assert not leftover, f"actor thread survived close(): {leftover}"


class TestDocumentRegistryRefresh:
    async def test_refresh_removes_documents_closed_outside_the_server(self, client, fake_factory):
        created = await new_document(client)
        document_id = document_id_of(created)

        listing = await call(client, "gcad_list_documents", {"refresh": True})
        assert not listing.is_error
        assert document_id in str(content(listing))

        # Simulate the document being closed behind the server's back.
        fake_document = fake_factory.app.Documents._items[-1]
        fake_factory.simulate_closed_document(fake_document)

        refreshed = await call(client, "gcad_list_documents", {"refresh": True})
        assert not refreshed.is_error
        payload = content(refreshed)
        assert document_id not in str(
            payload
        ), "stale document survived a registry refresh after external close"


async def _drain_actor_close(actor) -> None:
    close = getattr(actor, "close", None)
    if close is None:
        return
    try:
        await asyncio.wait_for(close(), timeout=10)
    except Exception:  # noqa: BLE001 - cleanup must not mask the test outcome
        pass
