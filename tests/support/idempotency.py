"""Thin constructor helper for the real ``IdempotencyStore`` (guideline §21)."""

from __future__ import annotations

from typing import Any

from gstarcad_mcp.policy.idempotency import IdempotencyStore


def make_store(
    state_dir: Any, *, retention_days: int = 30, max_records: int = 100_000
) -> IdempotencyStore:
    return IdempotencyStore(state_dir, retention_days=retention_days, max_records=max_records)
