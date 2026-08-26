"""Revision-conflict and limit-enforcement tests (guideline §22, §25.2, §16.14).

Driven through the public MCP surface with the fake CAD runtime.
"""

from __future__ import annotations

from support.configutil import with_overrides
from support.flows import (
    apply_batch,
    assert_tool_error,
    call,
    content,
    document_id_of,
    new_document,
    revision_of,
)
from support.harness import harness_for


class TestRevisionConflicts:
    async def test_stale_expected_revision_is_rejected(self, client):
        created = await new_document(client)
        document_id = document_id_of(created)

        result = await apply_batch(client, document_id, expected_revision=999)
        assert_tool_error(result, "DOCUMENT_CONFLICT")

    async def test_correct_revision_succeeds_then_conflicts_on_reuse(self, client):
        created = await new_document(client)
        document_id = document_id_of(created)

        first = await apply_batch(client, document_id, expected_revision=0)
        assert not first.is_error, f"batch at revision 0 failed: {first!r}"
        payload = content(first)
        assert revision_of(payload, "revision_before") == 0
        assert revision_of(payload) == 1

        second = await apply_batch(client, document_id, expected_revision=0)
        assert_tool_error(second, "DOCUMENT_CONFLICT")

    async def test_none_revision_skips_conflict_check(self, client):
        created = await new_document(client)
        document_id = document_id_of(created)
        await apply_batch(client, document_id, expected_revision=0)

        # Without expected_revision the stale value cannot conflict.
        result = await apply_batch(client, document_id, expected_revision=None)
        assert not result.is_error, f"batch without expected_revision failed: {result!r}"
        assert revision_of(content(result)) == 2

    async def test_read_only_tools_do_not_change_revision(self, client):
        created = await new_document(client)
        document_id = document_id_of(created)
        await apply_batch(client, document_id, expected_revision=0)

        for _ in range(3):
            listing = await call(client, "gcad_query_entities", {"document_id": document_id})
            assert not listing.is_error

        result = await apply_batch(client, document_id, expected_revision=1)
        assert not result.is_error, (
            "read-only queries must not advance the revision: "
            f"batch at revision 1 failed: {result!r}"
        )


class TestLimits:
    async def test_batch_over_schema_action_cap_rejected(self, client):
        created = await new_document(client)
        document_id = document_id_of(created)

        huge_batch = [
            {
                "op": "create_circle",
                "action_id": f"circle-{index}",
                "center": {"x": index, "y": 0, "z": 0},
                "radius": 1,
                "layer": "0",
            }
            for index in range(501)  # schema cap is 500 actions per batch
        ]
        result = await apply_batch(client, document_id, expected_revision=0, actions=huge_batch)
        assert result.is_error, "batch over the action-count cap must be rejected"

        # Rejection must happen before any mutation: revision stays at 0.
        retry = await apply_batch(client, document_id, expected_revision=0)
        assert not retry.is_error, (
            "an over-limit batch must not partially mutate the document: "
            f"revision 0 still expected afterwards, got: {retry!r}"
        )

    async def test_batch_action_limit_from_config_enforced_pre_mutation(
        self, server_config, fake_factory
    ):
        config = with_overrides(server_config, "limits", max_actions_per_batch=3)
        async with harness_for(config, fake_factory).client() as client:
            created = await new_document(client)
            document_id = document_id_of(created)

            actions = [
                {
                    "op": "create_circle",
                    "action_id": f"c-{i}",
                    "center": {"x": i, "y": 0, "z": 0},
                    "radius": 1,
                }
                for i in range(4)
            ]
            result = await apply_batch(client, document_id, expected_revision=0, actions=actions)
            assert_tool_error(result, "INVALID_ACTION")

            # Nothing was mutated.
            retry = await apply_batch(client, document_id, expected_revision=0)
            assert not retry.is_error

    async def test_polyline_vertex_limit_enforced(self, client):
        created = await new_document(client)
        document_id = document_id_of(created)

        points = [{"x": float(i), "y": float(i % 7), "z": 0.0} for i in range(10_001)]
        actions = [
            {
                "op": "create_polyline",
                "action_id": "too-many-vertices",
                "vertices": points,
                "closed": False,
                "layer": "0",
            }
        ]
        result = await apply_batch(client, document_id, expected_revision=0, actions=actions)
        assert_tool_error(result, "INVALID_ACTION")

    async def test_query_page_limit_enforced_by_schema(self, client):
        created = await new_document(client)
        document_id = document_id_of(created)
        result = await call(
            client,
            "gcad_query_entities",
            {"document_id": document_id, "limit": 1_000_000},
        )
        assert result.is_error, "query limit above the configured maximum must be rejected"

    async def test_query_page_limit_from_config(self, server_config, fake_factory):
        config = with_overrides(server_config, "limits", max_query_page_size=50)
        async with harness_for(config, fake_factory).client() as client:
            created = await new_document(client)
            document_id = document_id_of(created)
            result = await call(
                client,
                "gcad_query_entities",
                {"document_id": document_id, "limit": 100},  # schema allows <= 1000
            )
            assert_tool_error(result, "INVALID_ACTION")

    async def test_handles_per_request_limit(self, client):
        created = await new_document(client)
        document_id = document_id_of(created)
        handles = [format(i, "X") for i in range(1, 5001)]
        result = await call(
            client,
            "gcad_get_entities",
            {"document_id": document_id, "handles": handles},
        )
        assert (
            result.is_error
        ), "get_entities with more handles than the configured maximum must be rejected"

    async def test_handles_limit_from_config(self, server_config, fake_factory):
        config = with_overrides(server_config, "limits", max_entity_handles_per_request=5)
        async with harness_for(config, fake_factory).client() as client:
            created = await new_document(client)
            document_id = document_id_of(created)
            result = await call(
                client,
                "gcad_get_entities",
                {"document_id": document_id, "handles": [format(i, "X") for i in range(1, 7)]},
            )
            assert_tool_error(result, "INVALID_ACTION")
