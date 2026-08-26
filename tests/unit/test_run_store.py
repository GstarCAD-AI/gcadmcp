"""Run store durability tests (§20, §31.1): atomic manifest, append-only journal."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from support.harness import error_code_value

from gstarcad_mcp.errors import RUN_NOT_FOUND, ExpectedCadError
from gstarcad_mcp.runs.store import RunStore
from gstarcad_mcp.schemas.runs import RunManifest, RunStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _manifest(run_id: uuid.UUID | None = None) -> RunManifest:
    return RunManifest(
        run_id=run_id or uuid.uuid4(),
        runtime_id=uuid.uuid4(),
        status=RunStatus.RUNNING,
        title="Test run",
        intent="Draw a test plate with three holes.",
        created_at=_now(),
        updated_at=_now(),
    )


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs")


class TestCreateRun:
    def test_creates_dated_directory_with_subdirs(self, store: RunStore):
        manifest = _manifest()
        run_dir = store.create_run(manifest)
        assert run_dir.is_dir()
        assert (run_dir / "screenshots").is_dir()
        assert (run_dir / "outputs").is_dir()
        # Layout: runs/{YYYY-MM-DD}/{run_id}/
        assert run_dir.name == str(manifest.run_id)
        assert run_dir.parent.name == manifest.created_at.date().isoformat()

    def test_manifest_written_on_create(self, store: RunStore):
        manifest = _manifest()
        store.create_run(manifest)
        loaded = store.read_manifest(manifest.run_id)
        assert loaded.run_id == manifest.run_id
        assert loaded.title == manifest.title
        assert loaded.status == RunStatus.RUNNING
        assert loaded.schema_version == "1.0"

    def test_duplicate_create_rejected(self, store: RunStore):
        manifest = _manifest()
        store.create_run(manifest)
        with pytest.raises(OSError):
            store.create_run(manifest)


class TestAtomicManifest:
    def test_write_manifest_leaves_no_tmp_file(self, store: RunStore):
        manifest = _manifest()
        run_dir = store.create_run(manifest)
        manifest.status = RunStatus.SUCCEEDED
        manifest.artifacts["output-dwg"] = "outputs/final.dwg"
        store.write_manifest(manifest)

        assert not (run_dir / "manifest.json.tmp").exists()
        assert not list(run_dir.glob("*.tmp"))
        data = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert data["status"] == "succeeded"
        assert data["artifacts"]["output-dwg"] == "outputs/final.dwg"

    def test_manifest_is_valid_json_after_many_writes(self, store: RunStore):
        manifest = _manifest()
        run_dir = store.create_run(manifest)
        for i in range(5):
            manifest.artifacts[f"artifact-{i}"] = f"outputs/a{i}.json"
            store.write_manifest(manifest)
        data = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert len(data["artifacts"]) == 5

    def test_write_manifest_unknown_run_raises(self, store: RunStore):
        manifest = _manifest()
        with pytest.raises(ExpectedCadError) as excinfo:
            store.write_manifest(manifest)
        assert excinfo.value.code == error_code_value(RUN_NOT_FOUND)


class TestActionJournal:
    def test_append_only_growth(self, store: RunStore):
        manifest = _manifest()
        run_dir = store.create_run(manifest)
        journal = run_dir / "actions.jsonl"

        store.append_action(manifest.run_id, {"op": "create_circle", "index": 0})
        first = journal.read_bytes()
        store.append_action(manifest.run_id, {"op": "create_rect", "index": 1})
        second = journal.read_bytes()

        # Append-only: prior bytes are an exact prefix.
        assert second.startswith(first)
        lines = second.decode("utf-8").splitlines()
        assert len(lines) == 2
        for line in lines:
            row = json.loads(line)
            assert "timestamp" in row
            assert "op" in row

    def test_journal_rows_keep_inserted_fields(self, store: RunStore):
        manifest = _manifest()
        store.create_run(manifest)
        store.append_action(
            manifest.run_id,
            {"op": "create_segment", "action_id": "seg-1", "status": "succeeded"},
        )
        run_dir = store.run_dir(manifest.run_id)
        row = json.loads((run_dir / "actions.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert row["action_id"] == "seg-1"
        assert row["status"] == "succeeded"


class TestLookup:
    def test_run_dir_unknown_raises(self, store: RunStore):
        with pytest.raises(ExpectedCadError) as excinfo:
            store.run_dir(uuid.uuid4())
        assert excinfo.value.code == error_code_value(RUN_NOT_FOUND)

    def test_snapshot_path_and_exists(self, store: RunStore):
        manifest = _manifest()
        store.create_run(manifest)
        path = store.snapshot_path(manifest.run_id, "review")
        assert path.name == "review.png"
        assert not store.snapshot_exists(manifest.run_id, "review")
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        assert store.snapshot_exists(manifest.run_id, "review")

    def test_list_runs_newest_date_first(self, store: RunStore):
        manifest = _manifest()
        store.create_run(manifest)
        runs = store.list_runs()
        assert any(r["run_id"] == str(manifest.run_id) for r in runs)
