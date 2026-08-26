"""Document registry mapping server UUIDs to actor-owned COM documents (§12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from gstarcad_mcp.errors import DOCUMENT_NOT_FOUND, ExpectedCadError
from gstarcad_mcp.schemas.documents import DocumentOwnership, DocumentRef
from gstarcad_mcp.util.time import utc_now


@dataclass
class DocumentEntry:
    document_id: UUID
    raw_document: Any  # actor-thread only; never returned outside the actor
    name: str
    canonical_path: Path | None = None
    relative_path: str | None = None
    ownership: DocumentOwnership = DocumentOwnership.EXTERNAL
    read_only: bool = False
    revision: int = 0
    active: bool = False
    discovered_at: datetime = field(default_factory=utc_now)
    last_seen_at: datetime = field(default_factory=utc_now)
    external_change_suspected: bool = False

    def to_ref(self) -> DocumentRef:
        dirty: bool | None = None
        try:
            raw = self.raw_document
            if hasattr(raw, "Saved"):
                dirty = not bool(raw.Saved)
        except Exception:
            dirty = None
        return DocumentRef(
            document_id=self.document_id,
            name=self.name,
            relative_path=self.relative_path,
            ownership=self.ownership,
            read_only=self.read_only,
            active=self.active,
            revision=self.revision,
            dirty=dirty,
        )


class DocumentRegistry:
    """Actor-thread-only registry. Never expose raw documents."""

    def __init__(self) -> None:
        self._entries: dict[UUID, DocumentEntry] = {}
        self._by_path: dict[str, UUID] = {}

    def clear(self) -> None:
        self._entries.clear()
        self._by_path.clear()

    def add(self, entry: DocumentEntry) -> None:
        self._entries[entry.document_id] = entry
        if entry.canonical_path is not None:
            self._by_path[str(entry.canonical_path).lower()] = entry.document_id

    def get(self, document_id: UUID) -> DocumentEntry:
        entry = self._entries.get(document_id)
        if entry is None:
            raise ExpectedCadError(
                DOCUMENT_NOT_FOUND,
                "Unknown document_id. The server may have restarted (document ids do not "
                "survive restarts) or the document was closed. Call gcad_list_documents.",
            )
        return entry

    def find_by_path(self, path: Path) -> DocumentEntry | None:
        doc_id = self._by_path.get(str(path).lower())
        return self._entries.get(doc_id) if doc_id else None

    def remove(self, document_id: UUID) -> None:
        entry = self._entries.pop(document_id, None)
        if entry and entry.canonical_path is not None:
            self._by_path.pop(str(entry.canonical_path).lower(), None)

    def entries(self) -> list[DocumentEntry]:
        return list(self._entries.values())

    def count(self) -> int:
        return len(self._entries)

    def active_entry(self) -> DocumentEntry | None:
        for entry in self._entries.values():
            if entry.active:
                return entry
        return None

    def increment_revision(self, document_id: UUID) -> tuple[int, int]:
        entry = self.get(document_id)
        before = entry.revision
        entry.revision += 1
        return before, entry.revision

    def discover(self, cad_app: Any, *, ownership: DocumentOwnership) -> None:
        """Enumerate open COM documents and assign ids to unseen ones."""
        try:
            documents = cad_app.Documents
            count = int(documents.Count)
        except Exception:
            return
        active_raw = None
        try:
            active_raw = cad_app.ActiveDocument
        except Exception:
            active_raw = None
        active_key = _doc_key(active_raw) if active_raw is not None else None
        # COM wrappers are transient: match by stable (name, path) identity,
        # never by Python object identity.
        known_by_key = {_doc_key(e.raw_document): e.document_id for e in self._entries.values()}
        current_keys: set[tuple[str, str]] = set()
        for i in range(count):
            try:
                raw = documents.Item(i)
            except Exception:
                continue
            key = _doc_key(raw)
            current_keys.add(key)
            if key in known_by_key:
                entry = self._entries[known_by_key[key]]
                entry.raw_document = raw
                entry.last_seen_at = utc_now()
                entry.active = key == active_key
                continue
            name = _safe_name(raw)
            path = _safe_path(raw)
            entry = DocumentEntry(
                document_id=uuid4(),
                raw_document=raw,
                name=name,
                canonical_path=path,
                ownership=ownership,
            )
            entry.active = key == active_key
            self.add(entry)
        # remove entries whose document vanished (enumeration succeeded, so an
        # empty live list means every remaining entry is stale)
        for doc_id in [
            e.document_id
            for e in list(self._entries.values())
            if _doc_key(e.raw_document) not in current_keys
        ]:
            self.remove(doc_id)


def _doc_key(raw: Any) -> tuple[str, str]:
    """Stable identity for a COM document (wrappers are transient)."""
    path = _safe_path(raw)
    return (_safe_name(raw), str(path) if path else "")


def _safe_name(raw: Any) -> str:
    try:
        return str(raw.Name)
    except Exception:
        return "(unnamed)"


def _safe_path(raw: Any) -> Path | None:
    for attr in ("FullName", "Path"):
        try:
            value = getattr(raw, attr)
            if value:
                return Path(str(value))
        except Exception:
            continue
    return None
