"""gcadclaw workflow prompts (§19). Text loads from gcadclaw-assets; short fallback inline."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

try:
    from gcadclaw_assets import load_prompt as _load_asset
except ImportError:  # pragma: no cover - asset package always installed in supported envs
    _load_asset = None

_FALLBACK = {
    "create_2d_drawing": (
        "Create a 2D GstarCAD drawing: inspect status, begin a run, write the brief, "
        "capture before state, compute geometry explicitly, apply typed actions, "
        "inspect entities, capture a screenshot, review visually, repair the smallest "
        "responsible issue, then finalize with evidence."
    ),
    "modify_existing_drawing": (
        "Modify an existing drawing: identify the document and revision, capture before "
        "state, apply minimal typed actions with expected_revision, re-capture evidence, "
        "and finalize honestly."
    ),
    "mechanical_three_view": (
        "Produce a mechanical three-view drawing (top/front/right orthographic views) "
        "with dimensions and annotations on named layers, following the evidence loop."
    ),
    "review_and_repair": (
        "Review a drawing run and repair the smallest responsible issue. Failure classes: "
        "COM connection, source/action, geometry, layer/style, dimension/annotation, "
        "screenshot, save, policy/conflict. Recapture dependent evidence after repair."
    ),
    "finalize_with_evidence": (
        "Finalize a run: save the DWG, capture the final screenshot, refresh the entity "
        "inventory, validate, and report canonical artifacts. Never claim full success "
        "without them."
    ),
    "validate_before_delivery": (
        "Before delivery, validate the run: actions executed, entity inventory captured, "
        "layers present, screenshot exists and is a valid non-blank PNG, DWG saved after "
        "the last mutation, no partial commit unreported."
    ),
}


def _body(asset_name: str) -> str:
    if _load_asset is not None:
        try:
            return _load_asset(asset_name)
        except Exception:
            pass
    return _FALLBACK[asset_name]


def _task_block(**fields: str) -> str:
    lines = [f"- {name.replace('_', ' ')}: {value}" for name, value in fields.items() if value]
    return "## Task parameters\n\n" + "\n".join(lines)


def register_prompts(mcp: MCPServer) -> None:
    @mcp.prompt(
        name="gcad_create_2d_drawing",
        description="Brief-first workflow for creating a new 2D drawing with evidence.",
    )
    def create_2d_drawing(
        requirement: str,
        units: str = "millimeters",
        output_relative_path: str = "outputs/drawing.dwg",
        evidence_level: str = "standard",
        drafting_profile: str = "authoring",
    ) -> str:
        return (
            _body("create_2d_drawing")
            + "\n\n"
            + _task_block(
                requirement=requirement,
                units=units,
                output_relative_path=output_relative_path,
                evidence_level=evidence_level,
                drafting_profile=drafting_profile,
            )
        )

    @mcp.prompt(
        name="gcad_modify_existing_drawing",
        description="Workflow for modifying an existing drawing with revision safety.",
    )
    def modify_existing_drawing(requirement: str, document_hint: str = "") -> str:
        return (
            _body("modify_existing_drawing")
            + "\n\n"
            + _task_block(requirement=requirement, document_hint=document_hint)
        )

    @mcp.prompt(
        name="gcad_mechanical_three_view",
        description="Three-view orthographic mechanical drawing workflow.",
    )
    def mechanical_three_view(requirement: str, scale_hint: str = "1:1") -> str:
        return (
            _body("mechanical_three_view")
            + "\n\n"
            + _task_block(requirement=requirement, scale_hint=scale_hint)
        )

    @mcp.prompt(
        name="gcad_review_and_repair",
        description="Failure-class-driven review and smallest-responsible repair.",
    )
    def review_and_repair(requirement: str, run_hint: str = "") -> str:
        return (
            _body("review_and_repair")
            + "\n\n"
            + _task_block(requirement=requirement, run_hint=run_hint)
        )

    @mcp.prompt(
        name="gcad_finalize_with_evidence",
        description="Finalize a run and report the canonical artifact set.",
    )
    def finalize_with_evidence(run_hint: str = "") -> str:
        return _body("finalize_with_evidence") + "\n\n" + _task_block(run_hint=run_hint)

    @mcp.prompt(
        name="gcad_validate_before_delivery",
        description="Validation checklist to run before declaring delivery.",
    )
    def validate_before_delivery(run_hint: str = "") -> str:
        return _body("validate_before_delivery") + "\n\n" + _task_block(run_hint=run_hint)
