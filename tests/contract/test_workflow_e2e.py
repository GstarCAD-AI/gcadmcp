"""Canonical end-to-end workflow with the fake COM runtime (guideline §36).

Mirrors §36.1: status → run → document → before-state → batch from §36.2 →
query → capture view → save → evidence → validate → finalize → resources.
"""

from __future__ import annotations

import base64
import json
import uuid

import pytest
from support.flows import (
    EXAMPLE_BATCH_ACTIONS,
    apply_batch,
    call,
    content,
    document_id_of,
    new_document,
    revision_of,
)
from support.struct import (
    assert_no_absolute_paths,
    assert_no_stack_traces,
    deep_find,
    iter_strings,
)

pytestmark = pytest.mark.anyio

TRANSACTION_MODES = {"undo_group", "copy_on_write", "compensating_actions", "best_effort"}


def _resource_bytes(read_result) -> bytes:
    contents = getattr(read_result, "contents", None) or read_result
    item = contents[0]
    blob = getattr(item, "blob", None)
    if blob:
        return base64.b64decode(blob)
    text = getattr(item, "text", None)
    assert text is not None, f"resource content has neither blob nor text: {item!r}"
    return text.encode("utf-8")


class TestCanonicalWorkflow:
    async def test_full_fake_com_flow(self, client):
        # 1. status -----------------------------------------------------
        status = await call(client, "gcad_get_status", {})
        assert not status.is_error
        assert deep_find(content(status), "runtime_state") == "ready"

        # 2. document ----------------------------------------------------
        created = await new_document(client)
        document_id = document_id_of(created)

        # 3. begin run -----------------------------------------------------
        run = await call(
            client,
            "gcad_begin_run",
            {
                "operation_id": str(uuid.uuid4()),
                "document_id": document_id,
                "title": "Plate with two holes",
                "intent": "Draw an 80x50 plate with two 3mm holes.",
                "units": "millimeters",
                "assumptions": ["Units are millimeters."],
                "expected_outputs": ["outputs/final.dwg"],
            },
        )
        assert not run.is_error, f"gcad_begin_run failed: {run!r}"
        run_id = str(deep_find(content(run), "run_id"))
        assert run_id and run_id != "None"

        # 4. before state ---------------------------------------------------
        before = await call(
            client,
            "gcad_capture_before_state",
            {
                "operation_id": str(uuid.uuid4()),
                "run_id": run_id,
                "document_id": document_id,
            },
        )
        assert not before.is_error, f"gcad_capture_before_state failed: {before!r}"

        # 5. the §36.2 example batch ----------------------------------------
        batch = await apply_batch(client, document_id, expected_revision=0, run_id=run_id)
        assert not batch.is_error, f"example batch failed: {batch!r}"
        payload = content(batch)

        # §36.3: one revision transition 0 -> 1
        assert revision_of(payload, "revision_before") == 0
        assert revision_of(payload) == 1

        # §36.3: one result per action
        action_results = (
            deep_find(payload, "action_results")
            or deep_find(payload, "results")
            or deep_find(payload, "actions")
        )
        assert isinstance(action_results, list), f"no per-action results: {payload!r}"
        assert len(action_results) == len(EXAMPLE_BATCH_ACTIONS)

        # §36.3: handles for the created entities
        handles = deep_find(payload, "handles") or [
            handle
            for item in action_results
            if isinstance(item, dict)
            for handle in (item.get("handles") or [])
        ]
        assert handles, f"batch created entities but reported no handles: {payload!r}"

        # §36.3: honest transaction mode, no false atomicity claim
        mode = deep_find(payload, "transaction_mode")
        assert mode in TRANSACTION_MODES, f"unknown transaction_mode {mode!r}"
        if mode == "best_effort":
            warnings = deep_find(payload, "warnings") or []
            assert warnings, (
                "best_effort execution with atomic=True must warn that true "
                "atomicity was unavailable (§23.3, §36.3)"
            )

        # §36.3: no raw COM object crosses the boundary
        for text in iter_strings(payload):
            assert "FakeComObject" not in text and "COMObject" not in text

        # 6. query entities ---------------------------------------------------
        query = await call(client, "gcad_query_entities", {"document_id": document_id})
        assert not query.is_error
        entities = deep_find(content(query), "entities") or []
        assert (
            len(entities) >= 3
        ), f"expected at least rect + two circles, saw {len(entities)}: {entities!r}"
        assert deep_find(content(query), "revision") == 1

        # 7. capture view -------------------------------------------------------
        capture = await call(
            client,
            "gcad_capture_view",
            {
                "operation_id": str(uuid.uuid4()),
                "document_id": document_id,
                "run_id": run_id,
                "name": "review",
            },
        )
        assert not capture.is_error, f"gcad_capture_view failed: {capture!r}"
        snapshot = content(capture)
        assert deep_find(snapshot, "mime_type") == "image/png"
        resource_uri = deep_find(snapshot, "resource_uri")
        assert resource_uri and str(resource_uri).startswith("gcad://")

        # 8. read the screenshot resource -------------------------------------
        png = _resource_bytes(await client.read_resource(str(resource_uri)))
        assert png.startswith(b"\x89PNG"), "screenshot resource is not a PNG"
        assert deep_find(snapshot, "byte_size") == len(png)

        # 9. save -----------------------------------------------------------------
        saved = await call(
            client,
            "gcad_save_document",
            {
                "operation_id": str(uuid.uuid4()),
                "document_id": document_id,
                "expected_revision": 1,
                "mode": "save_as",
                "output_relative_path": "outputs/final.dwg",
                "overwrite": False,
            },
        )
        assert not saved.is_error, f"gcad_save_document failed: {saved!r}"

        # 10. evidence -------------------------------------------------------------
        evidence = await call(
            client,
            "gcad_collect_evidence",
            {
                "operation_id": str(uuid.uuid4()),
                "run_id": run_id,
                "document_id": document_id,
            },
        )
        assert not evidence.is_error, f"gcad_collect_evidence failed: {evidence!r}"

        # 11. validate ----------------------------------------------------------------
        validation = await call(
            client,
            "gcad_validate_run",
            {
                "operation_id": str(uuid.uuid4()),
                "run_id": run_id,
                "document_id": document_id,
            },
        )
        assert not validation.is_error, f"gcad_validate_run failed: {validation!r}"
        checks = deep_find(content(validation), "validations") or deep_find(
            content(validation), "checks"
        )
        assert checks, f"validation returned no checks: {content(validation)!r}"

        # 12. finalize -------------------------------------------------------------------
        final = await call(
            client,
            "gcad_finalize_run",
            {
                "operation_id": str(uuid.uuid4()),
                "run_id": run_id,
                "document_id": document_id,
            },
        )
        assert not final.is_error, f"gcad_finalize_run failed: {final!r}"
        final_status = deep_find(content(final), "status")
        assert final_status in (
            "succeeded",
            "partial",
            "failed",
        ), f"unexpected final run status {final_status!r}"

        # 13. run status + manifest resources -------------------------------------------
        run_status = await call(client, "gcad_get_run_status", {"run_id": run_id})
        assert not run_status.is_error

        manifest_bytes = _resource_bytes(
            await client.read_resource(f"gcad://runs/{run_id}/manifest")
        )
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        assert manifest["run_id"] == run_id
        assert manifest["schema_version"] == "1.0"
        assert manifest["status"] == final_status

        actions_bytes = _resource_bytes(await client.read_resource(f"gcad://runs/{run_id}/actions"))
        journal_lines = [
            line for line in actions_bytes.decode("utf-8").splitlines() if line.strip()
        ]
        assert journal_lines, "run journal is empty after a committed batch"
        for line in journal_lines:
            record = json.loads(line)
            assert "op" in record and "status" in record

        # Hygiene across every result in the flow -------------------------------
        for result in (
            status,
            created,
            run,
            before,
            batch,
            query,
            capture,
            saved,
            evidence,
            validation,
            final,
            run_status,
        ):
            assert_no_stack_traces(getattr(result, "content", []) or [])
            structured = getattr(result, "structured_content", None)
            if structured:
                assert_no_absolute_paths(structured)
