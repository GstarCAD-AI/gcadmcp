"""Document leases for future multi-client use (interfaces only, §22.3)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from gstarcad_mcp.schemas.common import StrictModel


class DocumentLease(StrictModel):
    lease_id: UUID
    document_id: UUID
    owner_principal: str
    acquired_at: datetime
    expires_at: datetime


class LeaseStore:
    """Not enabled in the MVP; possession of a lease id is never authentication."""

    def __init__(self) -> None:
        self._leases: dict[UUID, DocumentLease] = {}

    def acquire(self, lease: DocumentLease) -> None:
        self._leases[lease.document_id] = lease

    def release(self, document_id: UUID) -> None:
        self._leases.pop(document_id, None)

    def get(self, document_id: UUID) -> DocumentLease | None:
        return self._leases.get(document_id)
