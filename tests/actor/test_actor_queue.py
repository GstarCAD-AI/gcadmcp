"""Actor queue-limit and cancellation tests (guideline §10.7, §31.4)."""

from __future__ import annotations

import asyncio

import pytest
from fakes import FakeCadFactory
from support.configutil import with_overrides
from support.flows import call
from support.harness import error_code_value, harness_for

pytestmark = pytest.mark.anyio


def _collect_errors(outcomes: list) -> list[str]:
    texts: list[str] = []
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            texts.append(str(outcome))
        elif getattr(outcome, "is_error", False):
            for item in getattr(outcome, "content", []) or []:
                if getattr(item, "text", None):
                    texts.append(item.text)
    return texts


class TestQueueLimits:
    async def test_queue_full_returns_cad_queue_full(
        self, server_config, fake_factory: FakeCadFactory
    ):
        config = with_overrides(server_config, "cad", max_queue_depth=2)
        harness = harness_for(config, fake_factory)
        async with harness.client() as client:
            # Hold the actor thread so the bounded queue fills up.
            for method in ("Documents.Count", "Documents.Item", "Application.ActiveDocument"):
                fake_factory.recorder.delay(method, 0.15)
            try:
                tasks = [
                    asyncio.create_task(call(client, "gcad_list_documents", {"refresh": True}))
                    for _ in range(40)
                ]
                outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                for method in ("Documents.Count", "Documents.Item", "Application.ActiveDocument"):
                    fake_factory.recorder.no_delay(method)

        expected = error_code_value("CAD_QUEUE_FULL")
        errors = _collect_errors(list(outcomes))
        assert any(
            expected in text for text in errors
        ), f"no CAD_QUEUE_FULL surfaced when the queue overflowed; errors: {errors[:5]!r}"
        successes = [o for o in outcomes if not isinstance(o, BaseException) and not o.is_error]
        assert successes, "queued work should still succeed once the queue drains"

    async def test_queued_task_cancel_prevents_execution(
        self, server_config, fake_factory: FakeCadFactory
    ):
        import threading

        harness = harness_for(server_config, fake_factory)
        gate = threading.Event()
        async with harness.client() as client:
            fake_factory.recorder.block_until("Documents.Count", gate)
            try:
                blocker = asyncio.create_task(
                    call(client, "gcad_list_documents", {"refresh": True})
                )
                # Wait until the blocking call is actually in flight.
                for _ in range(100):
                    if fake_factory.recorder.calls_for("Documents.Count"):
                        break
                    await asyncio.sleep(0.02)
                assert fake_factory.recorder.calls_for("Documents.Count")

                queued = asyncio.create_task(
                    call(client, "gcad_new_document", {"operation_id": _uuid4()})
                )
                await asyncio.sleep(0.05)
                queued.cancel()
                with pytest.raises((asyncio.CancelledError, Exception)):
                    await queued
            finally:
                gate.set()
                fake_factory.recorder.unblock("Documents.Count")

            await asyncio.wait_for(blocker, timeout=15)

            # The cancelled operation must never have reached the COM layer.
            assert not fake_factory.recorder.calls_for(
                "Documents.Add"
            ), "cancelled queued work still executed on the actor thread"
            # The actor must still be healthy after a queue-side cancellation.
            healthy = await call(client, "gcad_list_documents", {"refresh": True})
            assert not healthy.is_error

    async def test_running_cancel_does_not_kill_actor_thread(
        self, server_config, fake_factory: FakeCadFactory
    ):
        import threading

        harness = harness_for(server_config, fake_factory)
        gate = threading.Event()
        async with harness.client() as client:
            fake_factory.recorder.block_until("Documents.Count", gate)
            try:
                task = asyncio.create_task(call(client, "gcad_list_documents", {"refresh": True}))
                for _ in range(100):
                    if fake_factory.recorder.calls_for("Documents.Count"):
                        break
                    await asyncio.sleep(0.02)
                task.cancel()
                await asyncio.sleep(0.05)
            finally:
                gate.set()
                fake_factory.recorder.unblock("Documents.Count")

            # Running work is allowed to finish; the actor must keep serving.
            follow_up = await asyncio.wait_for(
                call(client, "gcad_list_documents", {"refresh": True}), timeout=15
            )
            assert not follow_up.is_error, "actor thread died after a running cancellation"


def _uuid4() -> str:
    import uuid

    return str(uuid.uuid4())
