"""Durable run directories with atomic manifest writes (§20)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID

from gstarcad_mcp.errors import RUN_NOT_FOUND, ExpectedCadError
from gstarcad_mcp.schemas.runs import RunManifest, RunStatus
from gstarcad_mcp.util.time import utc_now


class RunStore:
    def __init__(self, runs_dir: Path):
        self.runs_dir = Path(runs_dir)

    def _run_dir(self, run_id: UUID) -> Path | None:
        if not self.runs_dir.exists():
            return None
        for day_dir in self.runs_dir.iterdir():
            candidate = day_dir / str(run_id)
            if candidate.is_dir():
                return candidate
        return None

    def run_dir(self, run_id: UUID) -> Path:
        found = self._run_dir(run_id)
        if found is None:
            raise ExpectedCadError(RUN_NOT_FOUND, f"Unknown run_id: {run_id}")
        return found

    def create_run(
        self,
        manifest: RunManifest | None = None,
        *,
        run_id: UUID | None = None,
        title: str | None = None,
        intent: str | None = None,
        units: str = "mm",
        runtime_id: UUID | None = None,
        document_id: UUID | None = None,
        status: Any = None,
    ) -> Path:
        if manifest is None:
            from uuid import uuid4

            now = utc_now()
            manifest = RunManifest(
                run_id=run_id or uuid4(),
                runtime_id=runtime_id or uuid4(),
                status=status or RunStatus.RUNNING,
                title=title or "Untitled run",
                intent=intent or "",
                units=units or "mm",
                document_id=document_id,
                created_at=now,
                updated_at=now,
            )
        day = manifest.created_at.date().isoformat()
        run_dir = self.runs_dir / day / str(manifest.run_id)
        run_dir.mkdir(parents=True, exist_ok=False)
        (run_dir / "screenshots").mkdir(exist_ok=True)
        (run_dir / "outputs").mkdir(exist_ok=True)
        self.write_manifest(manifest)
        return run_dir

    def update_manifest(
        self, run_id: UUID, updates: dict[str, Any] | None = None, **fields: Any
    ) -> RunManifest:
        manifest = self.read_manifest(run_id)
        for key, value in {**(updates or {}), **fields}.items():
            setattr(manifest, key, value)
        self.write_manifest(manifest)
        return manifest

    def write_manifest(self, manifest: RunManifest) -> None:
        run_dir = self.run_dir(manifest.run_id) if self._run_dir(manifest.run_id) else None
        if run_dir is None:
            raise ExpectedCadError(RUN_NOT_FOUND, f"Unknown run_id: {manifest.run_id}")
        manifest.updated_at = utc_now()
        payload = manifest.model_dump_json(indent=2)
        tmp = run_dir / "manifest.json.tmp"
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, run_dir / "manifest.json")

    def read_manifest(self, run_id: UUID) -> RunManifest:
        path = self.run_dir(run_id) / "manifest.json"
        return RunManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def append_action(self, run_id: UUID, row: dict[str, Any]) -> None:
        path = self.run_dir(run_id) / "actions.jsonl"
        row = {"timestamp": utc_now().isoformat(), **row}
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")

    def write_artifact(self, run_id: UUID, name: str, data: str | bytes) -> Path:
        run_dir = self.run_dir(run_id)
        path = run_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            path.write_text(data, encoding="utf-8")
        else:
            path.write_bytes(data)
        return path

    def write_brief(self, run_id: UUID, text: str) -> Path:
        return self.write_artifact(run_id, "brief.md", text)

    def artifact_path(self, run_id: UUID, name: str) -> Path:
        path = self.run_dir(run_id) / name
        if not path.exists():
            raise ExpectedCadError(RUN_NOT_FOUND, f"Run artifact not found: {name}")
        return path

    def snapshot_path(self, run_id: UUID, name: str) -> Path:
        path = self.run_dir(run_id) / "screenshots" / f"{name}.png"
        return path

    def snapshot_exists(self, run_id: UUID, name: str) -> bool:
        return self.snapshot_path(run_id, name).exists()

    def list_runs(self) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if not self.runs_dir.exists():
            return out
        for day_dir in sorted(self.runs_dir.iterdir(), reverse=True):
            if not day_dir.is_dir():
                continue
            for run_dir in sorted(day_dir.iterdir(), reverse=True):
                manifest = run_dir / "manifest.json"
                if manifest.exists():
                    out.append({"run_id": run_dir.name, "date": day_dir.name})
        return out

    def artifact_uri(self, run_id: UUID, artifact: str) -> str:
        return f"gcad://runs/{run_id}/{artifact}"
