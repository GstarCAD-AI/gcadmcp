"""Idempotency store semantics (§21, §31.1): replay, conflict, crash recovery."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from support.harness import error_code_value
from support.idempotency import make_store

from gstarcad_mcp.errors import (
    IDEMPOTENCY_CONFLICT,
    OPERATION_UNCERTAIN,
    ExpectedCadError,
)

TOOL = "gcad_new_document"


def _args(tag: str = "a") -> dict:
    return {"operation": tag, "value": 1}


class TestBeginComplete:
    def test_first_begin_returns_none(self, tmp_path: Path):
        store = make_store(tmp_path)
        op = uuid.uuid4()
        assert store.begin(TOOL, None, op, _args()) is None

    def test_second_begin_with_same_args_returns_prior(self, tmp_path: Path):
        store = make_store(tmp_path)
        op = uuid.uuid4()
        store.begin(TOOL, None, op, _args())
        prior = store.begin(TOOL, None, op, _args())
        assert prior is not None
        assert prior.operation_id == op
        assert prior.state == "in_progress"

    def test_same_operation_id_different_args_conflicts(self, tmp_path: Path):
        store = make_store(tmp_path)
        op = uuid.uuid4()
        store.begin(TOOL, None, op, _args("a"))
        with pytest.raises(ExpectedCadError) as excinfo:
            store.begin(TOOL, None, op, _args("b"))
        assert excinfo.value.code == error_code_value(IDEMPOTENCY_CONFLICT)
        # The client message must not leak stack traces.
        assert "Traceback" not in excinfo.value.client_message()

    def test_document_id_is_part_of_the_key(self, tmp_path: Path):
        store = make_store(tmp_path)
        op = uuid.uuid4()
        doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
        store.begin(TOOL, doc_a, op, _args())
        # Same operation_id under a different document is a different key.
        assert store.begin(TOOL, doc_b, op, _args()) is None

    def test_completed_result_is_replayed(self, tmp_path: Path):
        store = make_store(tmp_path)
        op = uuid.uuid4()
        store.begin(TOOL, None, op, _args())
        result = {"document_id": str(uuid.uuid4()), "status": "succeeded"}
        store.complete(TOOL, None, op, "succeeded", result)

        prior = store.begin(TOOL, None, op, _args())
        assert prior is not None
        assert prior.state == "succeeded"
        assert prior.result_json == result
        assert store.require_replay(prior) == result

    def test_failed_operation_can_be_reported_honestly(self, tmp_path: Path):
        store = make_store(tmp_path)
        op = uuid.uuid4()
        store.begin(TOOL, None, op, _args())
        store.complete(TOOL, None, op, "failed", None)
        prior = store.begin(TOOL, None, op, _args())
        assert prior is not None
        assert prior.state == "failed"


class TestCrashRecovery:
    def test_in_progress_becomes_uncertain_after_restart(self, tmp_path: Path):
        store = make_store(tmp_path)
        op = uuid.uuid4()
        store.begin(TOOL, None, op, _args())
        # Simulate a crash: no complete(), drop the store, reopen the dir.
        recovered = make_store(tmp_path)
        record = recovered.get(TOOL, None, op)
        assert record is not None
        assert record.state == "uncertain"

    def test_uncertain_operation_is_not_reported_succeeded(self, tmp_path: Path):
        store = make_store(tmp_path)
        op = uuid.uuid4()
        store.begin(TOOL, None, op, _args())
        recovered = make_store(tmp_path)

        # A replay attempt must either refuse with OPERATION_UNCERTAIN or at
        # least never claim success.
        prior = recovered.begin(TOOL, None, op, _args())
        if prior is None:
            pytest.fail("crashed operation_id must surface a prior record")
        assert prior.state != "succeeded"
        with pytest.raises(ExpectedCadError) as excinfo:
            recovered.require_replay(prior)
        assert excinfo.value.code == error_code_value(OPERATION_UNCERTAIN)
        assert excinfo.value.retryable is False

    def test_recovery_persists_uncertain_state(self, tmp_path: Path):
        store = make_store(tmp_path)
        op = uuid.uuid4()
        store.begin(TOOL, None, op, _args())
        make_store(tmp_path)  # recovery pass rewrites the journal
        third = make_store(tmp_path)
        record = third.get(TOOL, None, op)
        assert record is not None and record.state == "uncertain"


class TestJournal:
    def test_journal_is_append_only(self, tmp_path: Path):
        store = make_store(tmp_path)
        op = uuid.uuid4()
        store.begin(TOOL, None, op, _args())
        journal = tmp_path / "idempotency.jsonl"
        after_begin = journal.read_bytes()
        store.complete(TOOL, None, op, "succeeded", {"ok": True})
        after_complete = journal.read_bytes()
        assert after_complete.startswith(after_begin)
        assert after_complete.count(b"\n") == after_begin.count(b"\n") + 1

    def test_state_file_lives_in_workspace_state_dir(self, tmp_path: Path):
        store = make_store(tmp_path)
        store.begin(TOOL, None, uuid.uuid4(), _args())
        assert (tmp_path / "idempotency.jsonl").exists()
