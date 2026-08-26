"""Typed action models and tool request models (guidelines 8.6, 16)."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, PositiveFloat

from gstarcad_mcp.schemas.common import Point3, StrictModel


class ActionBase(StrictModel):
    action_id: str | None = Field(default=None, max_length=128)


class LayerSpec(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    color: int | None = Field(default=None, ge=0, le=256)
    lineweight: int | None = None


class _Styled(ActionBase):
    layer: str | None = Field(default=None, max_length=255)
    color: int | None = Field(default=None, ge=0, le=256)
    lineweight: int | None = None


class EnsureLayerAction(ActionBase):
    op: Literal["ensure_layer"] = "ensure_layer"
    name: str = Field(min_length=1, max_length=255)
    color: int | None = Field(default=None, ge=0, le=256)


class CreateSegmentAction(_Styled):
    op: Literal["create_segment"] = "create_segment"
    start: Point3
    end: Point3


class CreateCircleAction(_Styled):
    op: Literal["create_circle"] = "create_circle"
    center: Point3
    radius: PositiveFloat


class CreateArcAction(_Styled):
    op: Literal["create_arc"] = "create_arc"
    center: Point3
    radius: PositiveFloat
    start_angle: float = Field(description="Start angle in radians")
    end_angle: float = Field(description="End angle in radians")
    ccw: bool = True


class CreateEllipseAction(_Styled):
    op: Literal["create_ellipse"] = "create_ellipse"
    center: Point3
    semi_major: PositiveFloat
    semi_minor: PositiveFloat
    rotation: float = 0.0


class CreatePolylineAction(_Styled):
    op: Literal["create_polyline"] = "create_polyline"
    vertices: list[Point3] = Field(min_length=2)
    closed: bool = False


class CreateRectAction(_Styled):
    op: Literal["create_rect"] = "create_rect"
    corner1: Point3
    corner2: Point3


class CreateTextAction(ActionBase):
    op: Literal["create_text"] = "create_text"
    position: Point3
    text: str = Field(min_length=1, max_length=20_000)
    height: PositiveFloat
    rotation_deg: float = 0.0
    layer: str | None = Field(default=None, max_length=255)
    color: int | None = Field(default=None, ge=0, le=256)


class CreateHatchAction(ActionBase):
    op: Literal["create_hatch"] = "create_hatch"
    boundary_points: list[Point3] | None = Field(default=None, min_length=3)
    boundary_handles: list[str] | None = Field(default=None, min_length=1)
    pattern_name: str = Field(default="SOLID", max_length=128)
    scale: PositiveFloat = 1.0
    layer: str | None = Field(default=None, max_length=255)
    color: int | None = Field(default=None, ge=0, le=256)


class CreateDimensionAction(ActionBase):
    op: Literal["create_dimension"] = "create_dimension"
    pt1: Point3
    pt2: Point3
    dim_line_pt: Point3
    text: str | None = Field(default=None, max_length=2000)
    rotation: float | None = None
    layer: str | None = Field(default=None, max_length=255)
    color: int | None = Field(default=None, ge=0, le=256)


class CreateTableRow(StrictModel):
    cells: list[str] = Field(max_length=100)


class CreateTableAction(ActionBase):
    op: Literal["create_table"] = "create_table"
    position: Point3
    rows: int | None = Field(default=None, ge=1, le=200)
    columns: int | None = Field(default=None, ge=1, le=100)
    data: list[CreateTableRow] | None = None
    title: str | None = Field(default=None, max_length=500)
    row_height: PositiveFloat = 8.0
    col_width: PositiveFloat = 30.0
    text_height: PositiveFloat | None = None
    layer: str | None = Field(default=None, max_length=255)
    color: int | None = Field(default=None, ge=0, le=256)


class RegenAction(ActionBase):
    op: Literal["regen"] = "regen"
    mode: int = Field(default=1, ge=0, le=3)


class ZoomExtentsAction(ActionBase):
    op: Literal["zoom_extents"] = "zoom_extents"


CadAction = Annotated[
    EnsureLayerAction
    | CreateSegmentAction
    | CreateCircleAction
    | CreateArcAction
    | CreateEllipseAction
    | CreatePolylineAction
    | CreateRectAction
    | CreateTextAction
    | CreateHatchAction
    | CreateDimensionAction
    | CreateTableAction
    | RegenAction
    | ZoomExtentsAction,
    Field(discriminator="op"),
]

# --- tool request models ---


class NewDocumentRequest(StrictModel):
    operation_id: UUID
    template_relative_path: str | None = Field(default=None, max_length=1024)
    activate: bool = True


class OpenDocumentRequest(StrictModel):
    operation_id: UUID
    input_relative_path: str = Field(min_length=1, max_length=1024)
    read_only: bool = False
    activate: bool = True


class ActivateDocumentRequest(StrictModel):
    document_id: UUID
    expected_revision: int | None = Field(default=None, ge=0)


class SaveDocumentRequest(StrictModel):
    operation_id: UUID
    document_id: UUID
    expected_revision: int | None = Field(default=None, ge=0)
    mode: Literal["save", "save_as"] = "save"
    output_relative_path: str | None = Field(default=None, max_length=1024)
    overwrite: bool = False


class CloseDocumentRequest(StrictModel):
    operation_id: UUID
    document_id: UUID
    save_policy: Literal["reject_dirty", "save", "discard"] = "reject_dirty"


class EntityQuery(StrictModel):
    document_id: UUID
    layout: str | None = Field(default=None, max_length=255)
    entity_types: list[str] = Field(default_factory=list, max_length=32)
    layers: list[str] = Field(default_factory=list, max_length=64)
    handles: list[str] = Field(default_factory=list, max_length=500)
    text_contains: str | None = Field(default=None, max_length=512)
    cursor: str | None = Field(default=None, max_length=512)
    limit: int = Field(default=200, ge=1, le=1000)
    include_bounds: bool = False


class GetEntitiesRequest(StrictModel):
    document_id: UUID
    handles: list[str] = Field(min_length=1, max_length=1000)
    detail: Literal["summary", "full"] = "full"


class EnsureLayersRequest(StrictModel):
    operation_id: UUID
    document_id: UUID
    expected_revision: int | None = Field(default=None, ge=0)
    layers: list[LayerSpec] = Field(min_length=1, max_length=200)


class CreateEntitiesRequest(StrictModel):
    operation_id: UUID
    document_id: UUID
    expected_revision: int | None = Field(default=None, ge=0)
    entities: list[CadAction] = Field(min_length=1, max_length=500)


class ApplyActionsRequest(StrictModel):
    operation_id: UUID
    run_id: UUID | None = None
    document_id: UUID
    expected_revision: int | None = Field(default=None, ge=0)
    atomic: bool = True
    stop_on_error: bool = True
    actions: list[CadAction] = Field(min_length=1, max_length=500)


class CaptureViewRequest(StrictModel):
    operation_id: UUID
    document_id: UUID
    run_id: UUID | None = None
    name: str = Field(default="review", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    width: int | None = Field(default=None, ge=320, le=4096)
    height: int | None = Field(default=None, ge=240, le=4096)
    zoom: Literal["unchanged", "extents"] = "extents"


class BeginRunRequest(StrictModel):
    operation_id: UUID
    title: str = Field(min_length=1, max_length=500)
    intent: str = Field(min_length=1, max_length=20_000)
    document_id: UUID | None = None
    units: str = Field(default="mm", max_length=32)
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    expected_outputs: list[str] = Field(default_factory=list, max_length=50)


class CaptureBeforeStateRequest(StrictModel):
    operation_id: UUID
    run_id: UUID
    document_id: UUID
    layout: str | None = Field(default=None, max_length=255)
    screenshot: bool = True
    replace: bool = False


class CollectEvidenceRequest(StrictModel):
    operation_id: UUID
    run_id: UUID
    document_id: UUID
    layout: str | None = Field(default=None, max_length=255)
    screenshot: bool = True


class ValidateRunRequest(StrictModel):
    operation_id: UUID
    run_id: UUID
    document_id: UUID | None = None


class FinalizeRunRequest(StrictModel):
    operation_id: UUID
    run_id: UUID
    document_id: UUID | None = None
    output_relative_path: str | None = Field(default=None, max_length=1024)
    overwrite: bool = False
    screenshot_name: str = Field(default="final", pattern=r"^[A-Za-z0-9_-]{1,64}$")


class RunStatusRequest(StrictModel):
    run_id: UUID
