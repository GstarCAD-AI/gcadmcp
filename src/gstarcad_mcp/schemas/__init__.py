"""Strict Pydantic models for the MCP boundary (guideline 8)."""

from gstarcad_mcp.schemas.common import Bounds3, Point3, StrictModel
from gstarcad_mcp.schemas.documents import (
    DocumentOperationResult,
    DocumentOwnership,
    DocumentRef,
)
from gstarcad_mcp.schemas.entities import EntityRef
from gstarcad_mcp.schemas.results import (
    ActionResult,
    BatchOperationResult,
    ErrorInfo,
    GcadStatusResult,
    SnapshotResult,
)
from gstarcad_mcp.schemas.runs import RepairRecord, RunManifest, RunStatus, ValidationCheck

__all__ = [
    "ActionResult",
    "BatchOperationResult",
    "Bounds3",
    "DocumentOperationResult",
    "DocumentOwnership",
    "DocumentRef",
    "EntityRef",
    "ErrorInfo",
    "GcadStatusResult",
    "Point3",
    "RepairRecord",
    "RunManifest",
    "RunStatus",
    "SnapshotResult",
    "StrictModel",
    "ValidationCheck",
]
