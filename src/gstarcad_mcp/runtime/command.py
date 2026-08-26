"""Serializable command envelope (guideline 10.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True)
class CadCommand:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    document_id: UUID | None = None
    expected_revision: int | None = None
    run_id: UUID | None = None
    operation_id: UUID | None = None
    command_id: UUID = field(default_factory=uuid4)
    deadline_monotonic: float | None = None

    def __post_init__(self) -> None:
        from gstarcad_mcp.util.json import assert_wire_safe

        assert_wire_safe(self.payload)
