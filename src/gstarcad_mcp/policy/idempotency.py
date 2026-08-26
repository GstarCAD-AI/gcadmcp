"""Operation idempotency store (guideline 21)."""

from __future__ import annotations

import threading
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from gstarcad_mcp.errors import IDEMPOTENCY_CONFLICT, OPERATION_UNCERTAIN, ExpectedCadError
from gstarcad_mcp.util.json import request_hash
from gstarcad_mcp.util.time import utc_now

_PRINCIPAL = "local-stdio"


class IdempotencyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: UUID
    tool_name: str
    document_id: UUID | None = None
    request_hash: str
    state: str = "in_progress"  # in_progress|succeeded|partial|failed|uncertain
    result_json: dict | None = None
    created_at: str
    completed_at: str | None = None


class IdempotencyStore:
    """File-backed store keyed by principal+tool+document_id+operation_id."""

    def __init__(self, state_dir: Path, *, retention_days: int = 30, max_records: int = 100_000):
        self._dir = Path(state_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "idempotency.jsonl"
        self._lock = threading.Lock()
        self._retention = timedelta(days=retention_days)
        self._max_records = max_records
        self._records = self._load()

    def _load(self) -> dict[str, IdempotencyRecord]:
        records: dict[str, IdempotencyRecord] = {}
        if self._file.exists():
            for line in self._file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = IdempotencyRecord.model_validate_json(line)
                except ValueError:
                    continue
                if rec.state == "in_progress":
                    # Crash recovery (§21): an operation that was in flight
                    # when the process died must never be reported as
                    # succeeded; surface it as uncertain.
                    rec.state = "uncertain"
                records[self._key_of(rec)] = rec
        return records

    @staticmethod
    def _key_of(rec: IdempotencyRecord) -> str:
        return f"{_PRINCIPAL}|{rec.tool_name}|{rec.document_id}|{rec.operation_id}"

    def _key(self, tool_name: str, document_id: UUID | None, operation_id: UUID) -> str:
        return f"{_PRINCIPAL}|{tool_name}|{document_id}|{operation_id}"

    def _persist_append(self, rec: IdempotencyRecord) -> None:
        with open(self._file, "a", encoding="utf-8") as fh:
            fh.write(rec.model_dump_json() + "\n")

    def _persist_all(self) -> None:
        tmp = self._file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.writelines(rec.model_dump_json() + "\n" for rec in self._records.values())
        tmp.replace(self._file)

    def begin(
        self,
        tool_name: str,
        document_id: UUID | None,
        operation_id: UUID,
        request: dict,
    ) -> IdempotencyRecord | None:
        """Mark a mutation in progress.

        Returns ``None`` on first sight (the caller may proceed) or the
        stored prior record on replay (the caller decides whether to replay
        the stored result or raise). Raises ``IDEMPOTENCY_CONFLICT`` when
        the same key is reused with a different request hash.
        """
        digest = request_hash(request)
        key = self._key(tool_name, document_id, operation_id)
        with self._lock:
            existing = self._records.get(key)
            if existing is not None:
                if existing.request_hash != digest:
                    raise ExpectedCadError(
                        IDEMPOTENCY_CONFLICT,
                        "operation_id was already used with different arguments. "
                        "Generate a new operation_id for a different operation.",
                    )
                return existing
            rec = IdempotencyRecord(
                operation_id=operation_id,
                tool_name=tool_name,
                document_id=document_id,
                request_hash=digest,
                state="in_progress",
                created_at=utc_now().isoformat(),
            )
            self._records[key] = rec
            self._persist_append(rec)
            return None

    def complete(
        self,
        tool_name: str,
        document_id: UUID | None,
        operation_id: UUID,
        state: str,
        result: dict[str, Any] | None,
    ) -> None:
        with self._lock:
            rec = self._records.get(self._key(tool_name, document_id, operation_id))
            if rec is None:
                return
            rec.state = state
            rec.result_json = result
            rec.completed_at = utc_now().isoformat()
            self._persist_append(rec)
            self._prune_locked()

    def get(
        self, tool_name: str, document_id: UUID | None, operation_id: UUID
    ) -> IdempotencyRecord | None:
        with self._lock:
            return self._records.get(self._key(tool_name, document_id, operation_id))

    def require_replay(self, rec: IdempotencyRecord) -> dict:
        if rec.state in {"succeeded", "partial"} and rec.result_json is not None:
            return rec.result_json
        if rec.state == "uncertain":
            raise ExpectedCadError(
                OPERATION_UNCERTAIN,
                "A previous attempt with this operation_id ended uncertain after a crash. "
                "Inspect the document state before retrying; do not reuse the id blindly.",
                retryable=False,
            )
        raise ExpectedCadError(
            IDEMPOTENCY_CONFLICT,
            "operation_id is still in progress from another request.",
            retryable=True,
        )

    def _prune_locked(self) -> None:
        if len(self._records) <= self._max_records:
            return
        cutoff = utc_now() - self._retention
        dropped = []
        for key, rec in self._records.items():
            try:
                from datetime import datetime

                if datetime.fromisoformat(rec.created_at) < cutoff:
                    dropped.append(key)
            except ValueError:
                continue
        for key in dropped:
            del self._records[key]
        self._persist_all()
