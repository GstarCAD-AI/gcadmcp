"""Degraded-mode contract tests (guideline §13.1, §16.1).

When GstarCAD startup fails the server must stay available in a
diagnosable degraded state: status works, mutation tools fail cleanly.
"""

from __future__ import annotations

import uuid

import pytest
from fakes import FakeCadFactory
from support.configutil import make_expected_cad_error
from support.flows import call
from support.struct import deep_find

pytestmark = pytest.mark.anyio


@pytest.fixture
def degraded_factory() -> FakeCadFactory:
    return FakeCadFactory(
        startup_error=make_expected_cad_error("GstarCAD is not available in this test")
    )


@pytest.fixture
async def degraded_client(harness, degraded_factory):
    harness.cad_factory = degraded_factory
    async with harness.client() as value:
        yield value


class TestDegradedMode:
    async def test_status_still_works_when_cad_startup_failed(self, degraded_client):
        result = await call(degraded_client, "gcad_get_status", {})
        assert not result.is_error, "gcad_get_status must work in degraded mode (§16.1)"
        payload = result.structured_content
        state = deep_find(payload, "runtime_state")
        assert state in ("degraded", "failed"), f"unexpected runtime_state {state!r}"
        assert deep_find(payload, "connected") is False

    async def test_status_contains_diagnostic_warning(self, degraded_client):
        result = await call(degraded_client, "gcad_get_status", {})
        payload = result.structured_content
        warnings = deep_find(payload, "warnings") or []
        startup_error = deep_find(payload, "cad_startup_error")
        assert (
            warnings or startup_error
        ), "degraded status must surface a diagnostic warning or startup error"

    async def test_mutation_tools_fail_cleanly_in_degraded_mode(self, degraded_client):
        result = await call(
            degraded_client,
            "gcad_new_document",
            {"operation_id": str(uuid.uuid4())},
        )
        assert result.is_error, "mutations must fail while the runtime is degraded"
        for item in result.content:
            text = getattr(item, "text", "") or ""
            assert "Traceback" not in text

    async def test_listing_documents_reports_unavailable(self, degraded_client):
        result = await call(degraded_client, "gcad_list_documents", {"refresh": True})
        assert result.is_error, "document listing cannot succeed while the runtime is degraded"
