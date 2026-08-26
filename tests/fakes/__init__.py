"""Test fakes for the gstarcad-mcp-server suite."""

from .fake_com import (
    CallRecord,
    FakeCad,
    FakeCadFactory,
    FakeComClient,
    FakeComError,
    FakeDocument,
    FakeDocuments,
    FakeGstarCadApplication,
    FakeLayers,
    FakeLayouts,
    FakeModelSpace,
    FakePythonCom,
    FakeRecorder,
    FakeViewport,
)

__all__ = [
    "CallRecord",
    "FakeCad",
    "FakeCadFactory",
    "FakeComClient",
    "FakeComError",
    "FakeDocument",
    "FakeDocuments",
    "FakeGstarCadApplication",
    "FakeLayers",
    "FakeLayouts",
    "FakeModelSpace",
    "FakePythonCom",
    "FakeRecorder",
    "FakeViewport",
]
