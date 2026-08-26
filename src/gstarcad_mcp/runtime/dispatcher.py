"""Dispatcher: the only translator from server commands to pygcadwin (§11).

Runs exclusively on the actor thread. Never exposes raw COM objects.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from gstarcad_mcp.errors import (
    CAD_DISCONNECTED,
    DOCUMENT_DIRTY,
    ENTITY_NOT_FOUND,
    INVALID_ACTION,
    SAVE_FAILED,
    SCREENSHOT_FAILED,
    UNSUPPORTED_OPERATION,
    ExpectedCadError,
)
from gstarcad_mcp.runtime.command import CadCommand
from gstarcad_mcp.schemas.documents import DocumentOwnership

logger = logging.getLogger(__name__)


def _safe(value_fn, default=None):
    try:
        return value_fn()
    except Exception:
        return default


class CadDispatcher:
    def __init__(self, *, journal_writer: Callable[[dict], None] | None = None):
        self._journal_writer = journal_writer
        self._handlers: dict[str, Callable] = {
            "status": self._status,
            "list_documents": self._list_documents,
            "new_document": self._new_document,
            "open_document": self._open_document,
            "activate_document": self._activate_document,
            "save_document": self._save_document,
            "close_document": self._close_document,
            "list_layers": self._list_layers,
            "list_layouts": self._list_layouts,
            "query_entities": self._query_entities,
            "get_entities": self._get_entities,
            "ensure_layers": self._ensure_layers,
            "apply_actions": self._apply_actions,
            "capture_view": self._capture_view,
            "capture_inventory": self._capture_inventory,
        }

    def dispatch(self, runtime: Any, command: CadCommand) -> Any:
        handler = self._handlers.get(command.name)
        if handler is None:
            raise ExpectedCadError(UNSUPPORTED_OPERATION, f"Unknown command: {command.name}")
        try:
            return handler(runtime, command)
        except ExpectedCadError:
            raise
        except Exception as exc:
            text = str(exc)
            lowered = text.lower()
            if "disconnected" in lowered or "rpc" in lowered or "call was rejected" in lowered:
                raise ExpectedCadError(
                    CAD_DISCONNECTED, "GstarCAD COM connection was lost."
                ) from exc
            raise

    # -- helpers -------------------------------------------------------------

    def _entry(self, runtime: Any, document_id: UUID | None):
        if document_id is None:
            entries = runtime.registry.entries()
            if len(entries) == 1:
                return entries[0]
            raise ExpectedCadError(
                "DOCUMENT_NOT_FOUND",
                "document_id is required when zero or multiple documents are open.",
            )
        return runtime.registry.get(UUID(str(document_id)))

    def _context(self, runtime: Any, entry: Any):
        from pygcadwin import Context, Document

        doc = Document(entry.raw_document, owner=runtime.cad)
        return Context(doc), doc

    def _refresh(self, runtime: Any) -> None:
        runtime.registry.discover(runtime.cad.app, ownership=DocumentOwnership.EXTERNAL)

    def _entity_ref(self, raw: Any, document_id: UUID) -> dict:
        def read(attr):
            return _safe(lambda: getattr(raw, attr))

        object_name = read("ObjectName") or ""
        text = read("TextString")
        return {
            "document_id": str(document_id),
            "handle": str(read("Handle") or ""),
            "entity_type": str(object_name),
            "layer": _safe(lambda: str(raw.Layer)) if read("Layer") is not None else None,
            "color": read("Color"),
            "linetype": _safe(lambda: str(raw.Linetype)),
            "lineweight": read("LineWeight"),
            "closed": read("Closed"),
            "text": str(text) if text is not None else None,
            "bounds": None,
        }

    def _iter_entities(self, runtime: Any, entry: Any, layout: str | None = None):
        from pygcadwin import Document
        from pygcadwin.layouts import iter_layout_entities

        doc = Document(entry.raw_document, owner=runtime.cad)
        return iter_layout_entities(doc, layout=layout)

    def _find_by_handle(self, runtime: Any, entry: Any, handle: str, layout: str | None = None):
        for raw in self._iter_entities(runtime, entry, layout):
            if _safe(lambda: str(raw.Handle)) == handle:
                return raw
        return None

    # -- handlers --------------------------------------------------------------

    def _status(self, runtime: Any, command: CadCommand) -> dict:
        self._refresh(runtime)
        cad = runtime.cad
        active = runtime.registry.active_entry()
        return {
            "connected": True,
            "connection_mode": _safe(lambda: cad.connection_mode),
            "connected_prog_id": _safe(lambda: cad.prog_id),
            "application_responsive": _safe(lambda: bool(cad.app.Name), True),
            "active_document_id": str(active.document_id) if active else None,
            "document_count": runtime.registry.count(),
        }

    def _list_documents(self, runtime: Any, command: CadCommand) -> dict:
        self._refresh(runtime)
        return {
            "documents": [e.to_ref().model_dump(mode="json") for e in runtime.registry.entries()],
            "active_document_id": (
                str(a.document_id) if (a := runtime.registry.active_entry()) else None
            ),
        }

    def _new_document(self, runtime: Any, command: CadCommand) -> dict:
        template = command.payload.get("template_path")
        docs = runtime.cad.app.Documents
        raw = docs.Add(template) if template else docs.Add()
        from gstarcad_mcp.runtime.document_registry import DocumentEntry
        from gstarcad_mcp.util.ids import new_uuid

        entry = DocumentEntry(
            document_id=new_uuid(),
            raw_document=raw,
            name=_safe(lambda: str(raw.Name), "(unnamed)"),
            ownership=DocumentOwnership.SERVER,
            active=True,
        )
        for other in runtime.registry.entries():
            other.active = False
        runtime.registry.add(entry)
        return entry.to_ref().model_dump(mode="json")

    def _open_document(self, runtime: Any, command: CadCommand) -> dict:
        path = Path(command.payload["path"])
        existing = runtime.registry.find_by_path(path)
        if existing is not None:
            return existing.to_ref().model_dump(mode="json")
        raw = runtime.cad.app.Documents.Open(str(path))
        from gstarcad_mcp.runtime.document_registry import DocumentEntry
        from gstarcad_mcp.util.ids import new_uuid

        entry = DocumentEntry(
            document_id=new_uuid(),
            raw_document=raw,
            name=_safe(lambda: str(raw.Name), path.name),
            canonical_path=path,
            ownership=DocumentOwnership.SERVER,
            read_only=bool(command.payload.get("read_only", False)),
            active=True,
        )
        for other in runtime.registry.entries():
            other.active = False
        runtime.registry.add(entry)
        return entry.to_ref().model_dump(mode="json")

    def _activate_document(self, runtime: Any, command: CadCommand) -> dict:
        entry = self._entry(runtime, command.document_id)
        _safe(lambda: entry.raw_document.Activate())
        for other in runtime.registry.entries():
            other.active = other is entry
        return entry.to_ref().model_dump(mode="json")

    def _save_document(self, runtime: Any, command: CadCommand) -> dict:
        entry = self._entry(runtime, command.document_id)
        mode = command.payload.get("mode", "save")
        output_path = command.payload.get("output_path")
        try:
            if mode == "save_as":
                if not output_path:
                    raise ExpectedCadError(INVALID_ACTION, "save_as requires output_path.")
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                entry.raw_document.SaveAs(str(output_path))
                entry.canonical_path = Path(output_path)
                entry.name = _safe(lambda: str(entry.raw_document.Name), entry.name)
            else:
                entry.raw_document.Save()
        except ExpectedCadError:
            raise
        except Exception as exc:
            raise ExpectedCadError(SAVE_FAILED, f"Save failed: {exc}") from exc
        path: Path | None = entry.canonical_path
        result = {
            "document": entry.to_ref().model_dump(mode="json"),
            "saved_path_relative": command.payload.get("relative_path"),
            "byte_size": None,
            "modified_at": None,
        }
        if path is not None and path.exists():
            stat = path.stat()
            result["byte_size"] = stat.st_size
            result["modified_at"] = stat.st_mtime
        return result

    def _close_document(self, runtime: Any, command: CadCommand) -> dict:
        entry = self._entry(runtime, command.document_id)
        policy = command.payload.get("save_policy", "reject_dirty")
        dirty = _safe(lambda: not bool(entry.raw_document.Saved), False)
        if policy == "reject_dirty" and dirty:
            raise ExpectedCadError(
                DOCUMENT_DIRTY,
                "Document has unsaved changes. Save it first or pass save_policy='save'/'discard'.",
            )
        save_changes = policy == "save" and dirty
        entry.raw_document.Close(bool(save_changes))
        runtime.registry.remove(entry.document_id)
        return {"closed": True, "saved_before_close": bool(save_changes)}

    def _list_layers(self, runtime: Any, command: CadCommand) -> dict:
        entry = self._entry(runtime, command.document_id)
        layers_raw = entry.raw_document.Layers
        out = []
        count = _safe(lambda: int(layers_raw.Count), 0)
        for i in range(count):
            layer = _safe(lambda i=i: layers_raw.Item(i))
            if layer is None:
                continue
            out.append(
                {
                    "name": _safe(lambda: str(layer.Name)),
                    "color": _safe(lambda: int(layer.Color)),
                    "linetype": _safe(lambda: str(layer.Linetype)),
                    "lineweight": _safe(lambda: int(layer.LineWeight)),
                    "on": _safe(lambda: bool(layer.LayerOn)),
                    "frozen": _safe(lambda: bool(layer.Frozen)),
                    "locked": _safe(lambda: bool(layer.Locked)),
                    "plottable": _safe(lambda: bool(layer.Plottable)),
                }
            )
        return {"layers": out}

    def _list_layouts(self, runtime: Any, command: CadCommand) -> dict:
        entry = self._entry(runtime, command.document_id)
        layouts_raw = entry.raw_document.Layouts
        include_model = bool(command.payload.get("include_model", True))
        out = []
        count = _safe(lambda: int(layouts_raw.Count), 0)
        for i in range(count):
            layout = _safe(lambda i=i: layouts_raw.Item(i))
            if layout is None:
                continue
            tab_order = _safe(lambda: int(layout.TabOrder), 0)
            if tab_order == 0 and not include_model:
                continue
            out.append({"name": _safe(lambda: str(layout.Name)), "tab_order": tab_order})
        out.sort(key=lambda item: item["tab_order"])
        return {"layouts": out}

    def _query_entities(self, runtime: Any, command: CadCommand) -> dict:
        entry = self._entry(runtime, command.document_id)
        payload = command.payload
        offset = int(payload.get("offset", 0))
        limit = int(payload.get("limit", 200))
        entity_types = [t.lower() for t in payload.get("entity_types", [])]
        layers = {layer.lower() for layer in payload.get("layers", [])}
        handles = set(payload.get("handles", []))
        text_contains = payload.get("text_contains")

        collected = []
        for raw in self._iter_entities(runtime, entry, payload.get("layout")):
            ref = self._entity_ref(raw, entry.document_id)
            if entity_types and ref["entity_type"].lower() not in entity_types:
                continue
            if layers and (ref["layer"] or "").lower() not in layers:
                continue
            if handles and ref["handle"] not in handles:
                continue
            if text_contains and text_contains.lower() not in (ref["text"] or "").lower():
                continue
            collected.append(ref)
        collected.sort(key=lambda r: r["handle"])
        page = collected[offset : offset + limit]
        return {
            "entities": page,
            "next_offset": offset + limit if offset + limit < len(collected) else None,
            "total": len(collected),
            "revision": entry.revision,
        }

    def _get_entities(self, runtime: Any, command: CadCommand) -> dict:
        entry = self._entry(runtime, command.document_id)
        wanted = set(command.payload.get("handles", []))
        found = []
        missing = set(wanted)
        for raw in self._iter_entities(runtime, entry, command.payload.get("layout")):
            handle = _safe(lambda: str(raw.Handle))
            if handle in missing:
                found.append(self._entity_ref(raw, entry.document_id))
                missing.discard(handle)
                if not missing:
                    break
        return {"entities": found, "missing_handles": sorted(missing)}

    def _ensure_layers(self, runtime: Any, command: CadCommand) -> dict:
        entry = self._entry(runtime, command.document_id)
        ctx, _ = self._context(runtime, entry)
        results = []
        for spec in command.payload.get("layers", []):
            ctx.ensure_layer(spec["name"], color=spec.get("color"))
            results.append({"name": spec["name"], "ensured": True})
        return {"layers": results}

    def _apply_actions(self, runtime: Any, command: CadCommand) -> dict:
        entry = self._entry(runtime, command.document_id)
        ctx, doc = self._context(runtime, entry)
        revision_before = entry.revision
        action_results = []
        any_committed = False
        stop_on_error = bool(command.payload.get("stop_on_error", True))

        for index, action in enumerate(command.payload.get("actions", [])):
            op = action.get("op")
            action_id = action.get("action_id")
            started = time.monotonic()
            status = "succeeded"
            entities: list[dict] = []
            error = None
            try:
                created = self._run_action(runtime, entry, ctx, action)
                if created is not None:
                    if isinstance(created, list):
                        entities = created
                    else:
                        entities = [created]
                    any_committed = True
                elif op in {"regen", "zoom_extents"}:
                    any_committed = any_committed  # view ops do not bump revision alone
                else:
                    any_committed = True
            except ExpectedCadError as exc:
                status = "failed"
                error = {
                    "code": exc.code,
                    "message": exc.client_message(),
                    "retryable": exc.retryable,
                }
            except Exception as exc:
                status = "failed"
                error = {
                    "code": INVALID_ACTION,
                    "message": f"{type(exc).__name__}: {exc}",
                    "retryable": False,
                }
            duration_ms = int((time.monotonic() - started) * 1000)
            record = {
                "index": index,
                "action_id": action_id,
                "op": op,
                "status": status,
                "entities": entities,
                "handles": [str(handle) for e in entities if (handle := e.get("handle"))],
                "artifact_uris": [],
                "error": error,
                "duration_ms": duration_ms,
            }
            action_results.append(record)
            if self._journal_writer is not None:
                self._journal_writer(
                    {
                        "operation_id": str(command.operation_id) if command.operation_id else None,
                        "command_id": str(command.command_id),
                        "document_id": str(entry.document_id),
                        "run_id": str(command.run_id) if command.run_id else None,
                        "action_index": index,
                        "action_id": action_id,
                        "op": op,
                        "arguments": action,
                        "status": status,
                        "handles": [e.get("handle") for e in entities],
                        "duration_ms": duration_ms,
                        "error": error,
                    }
                )
            if status == "failed" and stop_on_error:
                for skipped_index in range(index + 1, len(command.payload.get("actions", []))):
                    skipped = command.payload["actions"][skipped_index]
                    action_results.append(
                        {
                            "index": skipped_index,
                            "action_id": skipped.get("action_id"),
                            "op": skipped.get("op"),
                            "status": "skipped",
                            "entities": [],
                            "handles": [],
                            "artifact_uris": [],
                            "error": None,
                            "duration_ms": 0,
                        }
                    )
                break

        if any_committed:
            revision_before, revision_after = runtime.registry.increment_revision(entry.document_id)
        else:
            revision_after = revision_before

        failed = [r for r in action_results if r["status"] == "failed"]
        return {
            "status": "succeeded" if not failed else "partial",
            "operation_id": str(command.operation_id) if command.operation_id else None,
            "document_id": str(entry.document_id),
            "revision_before": revision_before,
            "revision_after": revision_after,
            "transaction_mode": "best_effort",
            "rollback_status": "not_available" if failed and any_committed else "not_needed",
            "actions": action_results,
            "warnings": (
                [
                    "Requested atomicity could not be verified for this GstarCAD version; "
                    "batch executed best-effort."
                ]
                if command.payload.get("atomic", True)
                else []
            ),
        }

    def _run_action(self, runtime: Any, entry: Any, ctx: Any, action: dict) -> Any:
        op = action.get("op")
        style = {
            key: action.get(key)
            for key in ("layer", "color", "lineweight")
            if action.get(key) is not None
        }

        def pt(name: str):
            value = action[name]
            return (value["x"], value["y"], value.get("z", 0.0))

        if op == "ensure_layer":
            ctx.ensure_layer(action["name"], color=action.get("color"))
            return None
        if op == "create_segment":
            return self._ref(ctx.create_segment(pt("start"), pt("end"), **style), entry)
        if op == "create_circle":
            return self._ref(ctx.create_circle(pt("center"), action["radius"], **style), entry)
        if op == "create_arc":
            return self._ref(
                ctx.create_arc(
                    pt("center"),
                    action["radius"],
                    action["start_angle"],
                    action["end_angle"],
                    **style,
                ),
                entry,
            )
        if op == "create_ellipse":
            return self._ref(
                ctx.create_ellipse(
                    pt("center"),
                    action["semi_major"],
                    action["semi_minor"],
                    rotation=action.get("rotation", 0.0),
                    **style,
                ),
                entry,
            )
        if op == "create_polyline":
            vertices = [(v["x"], v["y"], v.get("z", 0.0)) for v in action["vertices"]]
            return self._ref(
                ctx.create_polyline(vertices, closed=action.get("closed", False), **style), entry
            )
        if op == "create_rect":
            return self._ref(ctx.create_rect(pt("corner1"), pt("corner2"), **style), entry)
        if op == "create_text":
            return self._ref(
                ctx.create_text(
                    pt("position"),
                    action["text"],
                    action["height"],
                    rotation_deg=action.get("rotation_deg", 0.0),
                    **{k: v for k, v in style.items() if k != "lineweight"},
                ),
                entry,
            )
        if op == "create_hatch":
            if action.get("boundary_points"):
                boundary = [(v["x"], v["y"], v.get("z", 0.0)) for v in action["boundary_points"]]
            elif action.get("boundary_handles"):
                boundary = []
                for handle in action["boundary_handles"]:
                    raw = self._find_by_handle(runtime, entry, handle)
                    if raw is None:
                        raise ExpectedCadError(
                            ENTITY_NOT_FOUND, f"Hatch boundary handle not found: {handle}"
                        )
                    boundary.append(raw)
            else:
                raise ExpectedCadError(INVALID_ACTION, "create_hatch requires a boundary.")
            return self._ref(
                ctx.create_hatch(
                    boundary,
                    pattern_name=action.get("pattern_name", "SOLID"),
                    scale=action.get("scale", 1.0),
                    **{k: v for k, v in style.items() if k != "lineweight"},
                ),
                entry,
            )
        if op == "create_dimension":
            return self._ref(
                ctx.create_dimension(
                    pt("pt1"),
                    pt("pt2"),
                    pt("dim_line_pt"),
                    text=action.get("text"),
                    rotation=action.get("rotation"),
                    **{k: v for k, v in style.items() if k != "lineweight"},
                ),
                entry,
            )
        if op == "create_table":
            data = [row["cells"] for row in action.get("data", [])] if action.get("data") else None
            return self._ref(
                ctx.create_table(
                    pt("position"),
                    rows=action.get("rows"),
                    columns=action.get("columns"),
                    data=data,
                    title=action.get("title"),
                    row_height=action.get("row_height", 8.0),
                    col_width=action.get("col_width", 30.0),
                    text_height=action.get("text_height"),
                    **{k: v for k, v in style.items() if k != "lineweight"},
                ),
                entry,
            )
        if op == "regen":
            ctx.regen(action.get("mode", 1))
            return None
        if op == "zoom_extents":
            ctx.zoom_extents()
            return None
        raise ExpectedCadError(UNSUPPORTED_OPERATION, f"Unsupported action: {op}")

    def _ref(self, entity: Any, entry: Any) -> dict:
        raw = getattr(entity, "raw", entity)
        return self._entity_ref(raw, entry.document_id)

    def _capture_view(self, runtime: Any, command: CadCommand) -> dict:
        entry = self._entry(runtime, command.document_id)
        _safe(lambda: entry.raw_document.Activate())
        ctx, _ = self._context(runtime, entry)
        try:
            snapshot = ctx.view.snapshot(
                width=command.payload.get("width"), height=command.payload.get("height")
            )
        except Exception as exc:
            raise ExpectedCadError(SCREENSHOT_FAILED, f"Screenshot capture failed: {exc}") from exc
        png = snapshot.to_png_bytes()
        dest = Path(command.payload["dest_path"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(png)
        import hashlib

        return {
            "document_id": str(entry.document_id),
            "revision": entry.revision,
            "relative_path": command.payload.get("relative_path", str(dest)),
            "width": snapshot.width,
            "height": snapshot.height,
            "byte_size": len(png),
            "sha256": hashlib.sha256(png).hexdigest(),
            "uniform": False,
        }

    def _capture_inventory(self, runtime: Any, command: CadCommand) -> dict:
        entry = self._entry(runtime, command.document_id)
        entities = []
        for raw in self._iter_entities(runtime, entry, command.payload.get("layout")):
            entities.append(
                {
                    "handle": _safe(lambda: str(raw.Handle)),
                    "object_name": _safe(lambda: str(raw.ObjectName)),
                    "layer": _safe(lambda: str(raw.Layer)),
                    "color": _safe(lambda: int(raw.Color)),
                    "linetype": _safe(lambda: str(raw.Linetype)),
                    "lineweight": _safe(lambda: int(raw.LineWeight)),
                    "closed": _safe(lambda: bool(raw.Closed)),
                    "text": _safe(lambda: str(raw.TextString)),
                }
            )
        from gstarcad_mcp.util.time import iso_now

        return {
            "document": entry.name,
            "layout": command.payload.get("layout") or "Model",
            "count": len(entities),
            "captured_at": iso_now(),
            "entities": entities,
        }
