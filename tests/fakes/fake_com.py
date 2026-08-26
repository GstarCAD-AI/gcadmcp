"""Reusable fake GstarCAD COM objects for the test suite (guideline §31.2).

Every fake COM method records:

- the method name;
- the positional/keyword arguments;
- the calling thread id;
- an optional injected error;
- a deterministic returned handle.

The fakes are plain Python objects that duck-type the GstarCAD COM surface
used by ``pygcadwin`` (``Gcad``/``Document``/``Context``/``View``) and by the
server's dispatcher; no real COM, GstarCAD, or Windows desktop is needed.
"""

from __future__ import annotations

import itertools
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class FakeComError(RuntimeError):
    """Raised by fakes when an error is injected."""


@dataclass(frozen=True)
class CallRecord:
    method: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    thread_id: int


@dataclass
class FakeRecorder:
    """Records fake COM calls and supports injected failures/blocking."""

    calls: list[CallRecord] = field(default_factory=list)
    _failures: dict[str, list[Exception]] = field(default_factory=dict)
    _blocks: dict[str, threading.Event] = field(default_factory=dict)
    _delays: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # -- recording ---------------------------------------------------------
    def record(self, method: str, *args: Any, **kwargs: Any) -> CallRecord:
        entry = CallRecord(
            method=method,
            args=tuple(args),
            kwargs=dict(kwargs),
            thread_id=threading.get_ident(),
        )
        with self._lock:
            self.calls.append(entry)
            delay = self._delays.get(method, 0.0)
        if delay:
            time.sleep(delay)
        block = self._blocks.get(method)
        if block is not None:
            block.wait(timeout=30)
        with self._lock:
            pending = self._failures.get(method)
            exc = pending.pop(0) if pending else None
        if exc is not None:
            raise exc
        return entry

    def calls_for(self, method: str) -> list[CallRecord]:
        with self._lock:
            return [c for c in self.calls if c.method == method]

    def prefixes(self, *prefixes: str) -> list[CallRecord]:
        with self._lock:
            return [c for c in self.calls if c.method.startswith(prefixes)]

    def thread_ids(self) -> set[int]:
        with self._lock:
            return {c.thread_id for c in self.calls}

    # -- fault injection ----------------------------------------------------
    def fail_next(self, method: str, exc: Exception) -> None:
        with self._lock:
            self._failures.setdefault(method, []).append(exc)

    def block_until(self, method: str, event: threading.Event) -> None:
        self._blocks[method] = event

    def unblock(self, method: str) -> None:
        self._blocks.pop(method, None)

    def delay(self, method: str, seconds: float) -> None:
        with self._lock:
            self._delays[method] = seconds

    def no_delay(self, method: str) -> None:
        with self._lock:
            self._delays.pop(method, None)


class _HandleSource:
    """Deterministic handle allocation, one sequence per document."""

    def __init__(self) -> None:
        self._counter = itertools.count(1)
        self._lock = threading.Lock()

    def next_handle(self) -> str:
        with self._lock:
            return format(next(self._counter), "X")


class FakeEntity:
    """A fake CAD entity with the common COM properties."""

    def __init__(
        self,
        recorder: FakeRecorder,
        object_name: str,
        handle: str,
        *,
        layer: str = "0",
        geometry: dict[str, Any] | None = None,
    ) -> None:
        self._recorder = recorder
        self.ObjectName = object_name
        self.Handle = handle
        self.Layer = layer
        self.Color = 256
        self.Linetype = "ByLayer"
        self.LineWeight = -1
        self.Visible = True
        self.Closed = False
        self.Deleted = False
        self.TextString: str | None = None
        self.geometry: dict[str, Any] = dict(geometry or {})

    def Delete(self) -> None:
        self._recorder.record("Entity.Delete", self.Handle)
        self.Deleted = True

    def Update(self) -> None:
        self._recorder.record("Entity.Update", self.Handle)

    def __setattr__(self, name: str, value: Any) -> None:
        # COM dispatch objects accept arbitrary property writes
        # (Rotation, TextOverride, ...); record style writes.
        super().__setattr__(name, value)

    def __repr__(self) -> str:  # COM-ish repr must never cross the boundary
        return f"<FakeComObject {self.ObjectName} {self.Handle}>"


class FakeHatch(FakeEntity):
    """Hatch entity supporting the boundary/style calls used by pygcadwin."""

    def __init__(self, recorder: FakeRecorder, handle: str, pattern_name: str) -> None:
        super().__init__(recorder, "AcDbHatch", handle)
        self.PatternName = pattern_name
        self.PatternScale = 1.0
        self.outer_loops: list[Any] = []
        self.evaluated = False

    def AppendOuterLoop(self, loop: Any) -> None:
        self._recorder.record("Hatch.AppendOuterLoop", self.Handle)
        self.outer_loops.append(loop)

    def Evaluate(self) -> None:
        self._recorder.record("Hatch.Evaluate", self.Handle)
        self.evaluated = True


class FakeTable(FakeEntity):
    """Table entity supporting the cell-text API used by pygcadwin.tables."""

    def __init__(self, recorder: FakeRecorder, handle: str, rows: int, columns: int) -> None:
        super().__init__(recorder, "AcDbTable", handle)
        self.Rows = rows
        self.Columns = columns
        self.cells: dict[tuple[int, int], str] = {}

    def SetText(self, row: int, column: int, text: str) -> None:
        self._recorder.record("Table.SetText", self.Handle, row, column, text)
        self.cells[(int(row), int(column))] = str(text)


class FakeLayer:
    def __init__(self, recorder: FakeRecorder, name: str) -> None:
        self._recorder = recorder
        self.Name = name
        self.Color = 7
        self.Linetype = "Continuous"
        self.LineWeight = -3
        self.LayerOn = True
        self.Frozen = False
        self.Locked = False
        self.Plottable = True


class FakeLayers:
    def __init__(self, recorder: FakeRecorder) -> None:
        self._recorder = recorder
        self._items: list[FakeLayer] = [FakeLayer(recorder, "0")]

    @property
    def Count(self) -> int:
        self._recorder.record("Layers.Count")
        return len(self._items)

    def Item(self, key: Any) -> FakeLayer:
        self._recorder.record("Layers.Item", key)
        if isinstance(key, int):
            return self._items[key]
        for layer in self._items:
            if layer.Name.lower() == str(key).lower():
                return layer
        raise FakeComError(f"Layer not found: {key}")

    def Add(self, name: str) -> FakeLayer:
        self._recorder.record("Layers.Add", name)
        try:
            return self.Item(name)
        except FakeComError:
            layer = FakeLayer(self._recorder, name)
            self._items.append(layer)
            return layer

    def __iter__(self) -> Iterable[FakeLayer]:
        return iter(list(self._items))

    def __getitem__(self, key: Any) -> FakeLayer:
        return self.Item(key)

    def __len__(self) -> int:
        return len(self._items)


class FakeLayout:
    def __init__(self, recorder: FakeRecorder, name: str, tab_order: int) -> None:
        self._recorder = recorder
        self.Name = name
        self.TabOrder = tab_order
        self.Block = FakeBlock(recorder, f"{name}-block")


class FakeBlock:
    def __init__(self, recorder: FakeRecorder, name: str) -> None:
        self._recorder = recorder
        self.Name = name
        self.entities: list[FakeEntity] = []

    @property
    def Count(self) -> int:
        return len(self.entities)

    def Item(self, index: int) -> FakeEntity:
        return self.entities[index]

    def __iter__(self) -> Iterable[FakeEntity]:
        return iter(list(self.entities))

    def __getitem__(self, index: int) -> FakeEntity:
        return self.entities[index]

    def __len__(self) -> int:
        return len(self.entities)


class FakeLayouts:
    def __init__(self, recorder: FakeRecorder) -> None:
        self._recorder = recorder
        self._items = [
            FakeLayout(recorder, "Model", 0),
            FakeLayout(recorder, "Layout1", 1),
        ]

    @property
    def Count(self) -> int:
        self._recorder.record("Layouts.Count")
        return len(self._items)

    def Item(self, key: Any) -> FakeLayout:
        self._recorder.record("Layouts.Item", key)
        if isinstance(key, int):
            return self._items[key]
        for layout in self._items:
            if layout.Name.lower() == str(key).lower():
                return layout
        raise FakeComError(f"Layout not found: {key}")

    def __iter__(self) -> Iterable[FakeLayout]:
        return iter(list(self._items))

    def __getitem__(self, key: Any) -> FakeLayout:
        return self.Item(key)

    def __len__(self) -> int:
        return len(self._items)


class FakeModelSpace:
    """Fake model space supporting the ``Add*`` creation methods used by pygcadwin."""

    def __init__(self, recorder: FakeRecorder, document: FakeDocument) -> None:
        self._recorder = recorder
        self._document = document
        self._handles = document._handles
        self.entities: list[FakeEntity] = []

    @property
    def Count(self) -> int:
        self._recorder.record("ModelSpace.Count")
        return len(self.entities)

    def Item(self, index: int) -> FakeEntity:
        self._recorder.record("ModelSpace.Item", index)
        return self.entities[index]

    def _commit(self, entity: FakeEntity) -> FakeEntity:
        self.entities.append(entity)
        self._document.saved = False
        return entity

    def _add(self, object_name: str, *args: Any, **geometry: Any) -> FakeEntity:
        self._recorder.record(f"ModelSpace.{object_name}", *args)
        entity = FakeEntity(
            self._recorder,
            object_name,
            self._handles.next_handle(),
            geometry=geometry,
        )
        return self._commit(entity)

    # Explicit, well-known creation methods.
    def AddLine(self, start: Any, end: Any) -> FakeEntity:
        return self._add("AcDbLine", start, end, start=start, end=end)

    def AddCircle(self, center: Any, radius: float) -> FakeEntity:
        return self._add("AcDbCircle", center, radius, center=center, radius=radius)

    def AddArc(
        self, center: Any, radius: float, start_angle: float, end_angle: float
    ) -> FakeEntity:
        return self._add(
            "AcDbArc",
            center,
            radius,
            start_angle,
            end_angle,
            center=center,
            radius=radius,
            start_angle=start_angle,
            end_angle=end_angle,
        )

    def AddEllipse(self, center: Any, major_axis: Any, radius_ratio: float) -> FakeEntity:
        return self._add(
            "AcDbEllipse",
            center,
            major_axis,
            radius_ratio,
            center=center,
            major_axis=major_axis,
            radius_ratio=radius_ratio,
        )

    def AddLightWeightPolyline(self, points: Any) -> FakeEntity:
        return self._add("AcDbPolyline", points, points=points)

    def AddPolyline(self, points: Any) -> FakeEntity:
        return self._add("AcDbPolyline", points, points=points)

    def AddText(self, text: str, insertion_point: Any, height: float) -> FakeEntity:
        entity = self._add(
            "AcDbText",
            text,
            insertion_point,
            height,
            text=text,
            insertion_point=insertion_point,
            height=height,
        )
        entity.TextString = str(text)
        return entity

    def AddMText(self, insertion_point: Any, width: float, text: str) -> FakeEntity:
        entity = self._add(
            "AcDbMText",
            insertion_point,
            width,
            text,
            insertion_point=insertion_point,
            width=width,
            text=text,
        )
        entity.TextString = str(text)
        return entity

    def AddHatch(self, hatch_type: Any, pattern_name: str, associativity: Any) -> FakeHatch:
        self._recorder.record("ModelSpace.AddHatch", hatch_type, pattern_name, associativity)
        hatch = FakeHatch(self._recorder, self._handles.next_handle(), str(pattern_name))
        return self._commit(hatch)  # type: ignore[return-value]

    def AddDimRotated(self, *args: Any) -> FakeEntity:
        return self._add("AcDbRotatedDimension", *args)

    def AddDimAligned(self, *args: Any) -> FakeEntity:
        return self._add("AcDbAlignedDimension", *args)

    def AddTable(self, position: Any, rows: int, columns: int, *args: Any) -> FakeTable:
        self._recorder.record("ModelSpace.AddTable", position, rows, columns, *args)
        table = FakeTable(self._recorder, self._handles.next_handle(), int(rows), int(columns))
        return self._commit(table)  # type: ignore[return-value]

    def __getattr__(self, name: str) -> Any:
        # Generic fallback for any other Add* creation method.
        if name.startswith("Add"):
            object_name = "AcDb" + name[3:]

            def _generic(*args: Any) -> FakeEntity:
                return self._add(object_name, *args)

            return _generic
        raise AttributeError(name)

    def __iter__(self) -> Iterable[FakeEntity]:
        return iter(list(self.entities))

    def __getitem__(self, index: int) -> FakeEntity:
        return self.entities[index]

    def __len__(self) -> int:
        return len(self.entities)


class FakeViewport:
    def __init__(self, recorder: FakeRecorder) -> None:
        self._recorder = recorder
        self.Width = 1280
        self.Height = 800

    def ZoomExtents(self) -> None:
        self._recorder.record("Viewport.ZoomExtents")


class FakeDocument:
    """A fake open drawing."""

    def __init__(self, recorder: FakeRecorder, name: str, full_name: str = "") -> None:
        self._recorder = recorder
        self._handles = _HandleSource()
        self.Name = name
        self.FullName = full_name or name
        self.Path = str(full_name).rsplit("\\", 1)[0] if "\\" in str(full_name) else ""
        self.Layers = FakeLayers(recorder)
        self.Layouts = FakeLayouts(recorder)
        self.ModelSpace = FakeModelSpace(recorder, self)
        self.ActiveLayout = self.Layouts.Item("Model")
        self.ActiveLayer: FakeLayer = self.Layers.Item(0)
        self.Viewport = FakeViewport(recorder)
        self.saved = True
        self.closed = False
        self._saved_as: str | None = None

    @property
    def Saved(self) -> bool:
        return self.saved

    def Activate(self) -> None:
        self._recorder.record("Document.Activate", self.Name)

    def Save(self) -> None:
        self._recorder.record("Document.Save", self.Name)
        self.saved = True

    def SaveAs(self, path: str, *args: Any) -> None:
        self._recorder.record("Document.SaveAs", path, *args)
        self._saved_as = path
        # Materialize a non-empty file so save/evidence checks can see it.
        target = Path(path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"AC1032 fake-gstarcad-dwg " + str(self.Name).encode())
        except OSError:
            pass
        self.FullName = path
        self.Name = str(path).replace("/", "\\").rsplit("\\", 1)[-1]
        self.Path = str(target.parent)
        self.saved = True

    def Close(self, save_changes: bool = False, *args: Any) -> None:
        self._recorder.record("Document.Close", save_changes, *args)
        self.closed = True

    def Regen(self, mode: int = 1) -> None:
        self._recorder.record("Document.Regen", mode)

    def GetVariable(self, name: str) -> Any:
        self._recorder.record("Document.GetVariable", name)
        return {"DWGNAME": self.Name, "DWGPREFIX": self.Path}.get(name, 0)

    def HandleToEntity(self, handle: str) -> FakeEntity:
        self._recorder.record("Document.HandleToEntity", handle)
        for entity in self.ModelSpace.entities:
            if entity.Handle == handle:
                return entity
        raise FakeComError(f"Entity not found: {handle}")


class FakeDocuments:
    """Fake ``Documents`` collection on the application (0-based ``Item``)."""

    def __init__(self, recorder: FakeRecorder) -> None:
        self._recorder = recorder
        self._items: list[FakeDocument] = []
        self._counter = itertools.count(1)

    @property
    def Count(self) -> int:
        self._recorder.record("Documents.Count")
        return len(self._items)

    def Item(self, key: Any) -> FakeDocument:
        self._recorder.record("Documents.Item", key)
        if isinstance(key, int):
            return self._items[key]
        for document in self._items:
            if document.Name.lower() == str(key).lower():
                return document
        raise FakeComError(f"Document not found: {key}")

    def Add(self, template: str | None = None) -> FakeDocument:
        self._recorder.record("Documents.Add", template)
        number = next(self._counter)
        document = FakeDocument(self._recorder, f"Drawing{number}.dwg")
        self._items.append(document)
        return document

    def Open(self, path: str, *args: Any) -> FakeDocument:
        self._recorder.record("Documents.Open", path, *args)
        name = str(path).replace("/", "\\").rsplit("\\", 1)[-1]
        for document in self._items:
            if document.FullName == path or document.Name == name:
                return document
        document = FakeDocument(self._recorder, name, full_name=path)
        self._items.append(document)
        return document

    def remove(self, document: FakeDocument) -> None:
        """Simulate the document disappearing from GstarCAD."""
        self._items.remove(document)

    def __iter__(self) -> Iterable[FakeDocument]:
        return iter(list(self._items))

    def __getitem__(self, key: Any) -> FakeDocument:
        return self.Item(key)

    def __len__(self) -> int:
        return len(self._items)


class FakeGstarCadApplication:
    """Fake GstarCAD application object."""

    def __init__(self, recorder: FakeRecorder) -> None:
        self._recorder = recorder
        self.Documents = FakeDocuments(recorder)
        self.Visible = True
        self.Name = "GstarCAD"
        self.Version = "27.0-fake"
        self.HWND = 987654  # window handle used by the stubbed snapshot path
        self._active: FakeDocument | None = None
        self.quit_called = False

    @property
    def ActiveDocument(self) -> FakeDocument:
        self._recorder.record("Application.ActiveDocument")
        if self._active is not None and not self._active.closed:
            return self._active
        for document in self.Documents:
            if not document.closed:
                return document
        raise FakeComError("No open documents")

    @ActiveDocument.setter
    def ActiveDocument(self, document: FakeDocument) -> None:
        self._recorder.record("Application.SetActiveDocument", document.Name)
        self._active = document

    def ZoomExtents(self) -> None:
        self._recorder.record("Application.ZoomExtents")

    def ZoomAll(self) -> None:
        self._recorder.record("Application.ZoomAll")

    def Quit(self) -> None:
        self._recorder.record("Application.Quit")
        self.quit_called = True

    def Update(self) -> None:
        self._recorder.record("Application.Update")


class FakePythonCom:
    """Minimal stand-in for the ``pythoncom`` module."""

    VT_ARRAY = 0x2000
    VT_R8 = 5
    VT_I4 = 3
    VT_I2 = 2
    VT_BSTR = 8
    VT_DISPATCH = 9
    VT_VARIANT = 12
    CLSCTX_LOCAL_SERVER = 4

    def __init__(self, recorder: FakeRecorder) -> None:
        self._recorder = recorder
        self.initialized_threads: list[int] = []
        self.uninitialized_threads: list[int] = []

    def CoInitialize(self, *args: Any) -> None:
        self._recorder.record("pythoncom.CoInitialize", *args)
        self.initialized_threads.append(threading.get_ident())

    def CoInitializeEx(self, *args: Any) -> None:
        self._recorder.record("pythoncom.CoInitializeEx", *args)
        self.initialized_threads.append(threading.get_ident())

    def CoUninitialize(self) -> None:
        self._recorder.record("pythoncom.CoUninitialize")
        self.uninitialized_threads.append(threading.get_ident())

    def CoCreateInstance(self, *args: Any) -> Any:
        self._recorder.record("pythoncom.CoCreateInstance", *args)
        raise FakeComError("FakePythonCom does not create instances")


class FakeComClient:
    """Minimal stand-in for ``win32com.client``."""

    def __init__(self, recorder: FakeRecorder, app: FakeGstarCadApplication) -> None:
        self._recorder = recorder
        self._app = app
        self._pythoncom = FakePythonCom(recorder)
        self.active_available = True
        self.dispatch_allowed = True

    def GetActiveObject(self, prog_id: str) -> FakeGstarCadApplication:
        self._recorder.record("win32com.client.GetActiveObject", prog_id)
        if not self.active_available:
            raise FakeComError(f"No active object for {prog_id}")
        return self._app

    def Dispatch(self, prog_id: str) -> FakeGstarCadApplication:
        self._recorder.record("win32com.client.Dispatch", prog_id)
        if not self.dispatch_allowed:
            raise FakeComError(f"Cannot dispatch {prog_id}")
        return self._app

    def VARIANT(self, vt: int, value: Any) -> Any:
        self._recorder.record("win32com.client.VARIANT", vt)
        return value

    def GetBestInterface(self, obj: Any) -> Any:
        return obj


class FakeCad:
    """A ``pygcadwin.Gcad``-shaped facade over the fake COM application.

    The harness hands this object to the server's CAD factory seam so no real
    GstarCAD is needed.  It exposes the attributes the dispatcher and
    ``pygcadwin`` wrappers rely on: ``app``, ``connection_mode``, ``prog_id``,
    ``_app``, ``_com_client``, ``_pythoncom``, and ``close()``.
    """

    def __init__(
        self,
        app: FakeGstarCadApplication,
        recorder: FakeRecorder,
        com_client: FakeComClient,
    ) -> None:
        self._app = app
        self.app = app
        self.recorder = recorder
        self._com_client = com_client
        self._pythoncom = com_client._pythoncom
        self.prog_id = "GStarCAD.Application"
        self.connection_mode = "attached"
        self.connected = False
        self.closed = False

    def connect(self) -> FakeGstarCadApplication:
        self.recorder.record("FakeCad.connect")
        self.connected = True
        return self.app

    def close(self) -> None:
        self.recorder.record("FakeCad.close")
        self.closed = True

    def __enter__(self) -> FakeCad:
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


@dataclass
class FakeCadFactory:
    """Callable CAD factory for the actor seam.

    Call ``factory()`` to obtain a connected :class:`FakeCad`.  Set
    ``startup_error`` to simulate a GstarCAD startup failure.
    """

    startup_error: Exception | None = None
    recorder: FakeRecorder = field(default_factory=FakeRecorder)
    app: FakeGstarCadApplication = field(init=False)
    created: list[FakeCad] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.app = FakeGstarCadApplication(self.recorder)
        self.com_client = FakeComClient(self.recorder, self.app)
        self.pythoncom = self.com_client._pythoncom

    def __call__(self, *args: Any, **kwargs: Any) -> FakeCad:
        self.recorder.record("CadFactory.__call__")
        if self.startup_error is not None:
            raise self.startup_error
        cad = FakeCad(self.app, self.recorder, self.com_client)
        cad.connect()
        self.created.append(cad)
        return cad

    # Convenience constructors used by tests.
    def new_document(self, name: str = "Drawing1.dwg") -> FakeDocument:
        return self.app.Documents.Add()

    def simulate_closed_document(self, document: FakeDocument) -> None:
        """Make a document disappear from the application (registry refresh)."""
        document.closed = True
        self.app.Documents.remove(document)
