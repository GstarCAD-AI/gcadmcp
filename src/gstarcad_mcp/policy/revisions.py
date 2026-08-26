"""Revision conflict checks (guideline 22)."""

from __future__ import annotations

from gstarcad_mcp.errors import DOCUMENT_CONFLICT, DocumentConflictError


def check_expected_revision(expected: int | None, actual: int, *, document_label: str) -> None:
    if expected is None:
        return
    if expected != actual:
        raise DocumentConflictError(
            DOCUMENT_CONFLICT,
            f"DOCUMENT_CONFLICT on {document_label}: expected revision {expected}, "
            f"actual revision {actual}. Refresh the document summary and re-plan the edit.",
            context={"expected_revision": expected, "actual_revision": actual},
        )
