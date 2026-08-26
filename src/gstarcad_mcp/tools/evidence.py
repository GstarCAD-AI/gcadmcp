"""Evidence tools: screenshots, runs, validation, finalization (§16.18-16.24)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from gstarcad_mcp.app_context import AppContext
from gstarcad_mcp.errors import ExpectedCadError
from gstarcad_mcp.policy.permissions import check_permission
from gstarcad_mcp.runs.validation import validate_run
from gstarcad_mcp.runtime.command import CadCommand
from gstarcad_mcp.schemas.results import SnapshotResult
from gstarcad_mcp.schemas.runs import RunManifest, RunStatus, ValidationCheck
from gstarcad_mcp.schemas.tools import (
    BeginRunRequest,
    CaptureBeforeStateRequest,
    CaptureViewRequest,
    CollectEvidenceRequest,
    FinalizeRunRequest,
    RunStatusRequest,
    ValidateRunRequest,
)
from gstarcad_mcp.tools._helpers import get_state, map_error, run_command, with_idempotency
from gstarcad_mcp.util.time import utc_now

MUTATING = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)


class BeginRunResult(BaseModel):
    run_id: UUID
    runtime_id: UUID
    status: RunStatus
    manifest_uri: str
    document_id: UUID | None = None


class EvidenceResult(BaseModel):
    run_id: UUID
    document_id: UUID
    artifacts: dict[str, str] = Field(default_factory=dict)
    entity_count: int = 0


class ValidateRunResult(BaseModel):
    run_id: UUID
    checks: list[ValidationCheck]
    overall: str


class FinalizeRunResult(BaseModel):
    run_id: UUID
    status: RunStatus
    manifest_uri: str
    artifacts: dict[str, str] = Field(default_factory=dict)
    checks: list[ValidationCheck] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RunStatusResult(BaseModel):
    run_id: UUID
    status: RunStatus
    title: str
    artifacts: dict[str, str] = Field(default_factory=dict)


async def _capture_view_core(state: AppContext, request: CaptureViewRequest) -> SnapshotResult:
    try:
        state.limits.check_screenshot_size(request.width, request.height)
    except ExpectedCadError as exc:
        raise map_error(exc) from exc
    if request.run_id is not None:
        dest = state.run_store.snapshot_path(request.run_id, request.name)
        relative = f"runs screenshots/{request.name}.png"
        uri = f"gcad://runs/{request.run_id}/snapshots/{request.name}"
    else:
        dest = state.workspace.cache_dir / f"{request.document_id}-{request.name}.png"
        relative = state.workspace.relative(dest) if dest.exists() else f"cache/{dest.name}"
        uri = f"gcad://documents/{request.document_id}/snapshot/latest"
    result = await run_command(
        state,
        CadCommand(
            name="capture_view",
            document_id=request.document_id,
            run_id=request.run_id,
            payload={
                "dest_path": str(dest),
                "relative_path": relative,
                "width": request.width,
                "height": request.height,
                "zoom": request.zoom,
                "name": request.name,
            },
        ),
    )
    state.audit.record("cad.snapshot", document_id=str(request.document_id), path=relative)
    return SnapshotResult(
        document_id=request.document_id,
        revision=result.get("revision", 0),
        resource_uri=uri,
        relative_path=result.get("relative_path", relative),
        width=result["width"],
        height=result["height"],
        byte_size=result["byte_size"],
        sha256=result.get("sha256"),
        uniform=result.get("uniform", False),
        captured_at=utc_now(),
    )


def register_evidence_tools(mcp) -> None:
    @mcp.tool(
        name="gcad_capture_view",
        title="Capture a viewport screenshot",
        description=(
            "Capture the requested document's viewport as PNG evidence. Activates the document "
            "and zooms to extents by default. Returns a resource URI; blank/uniform captures are "
            "flagged."
        ),
        annotations=MUTATING,
        structured_output=True,
    )
    async def gcad_capture_view(
        ctx: Context[AppContext],
        operation_id: UUID,
        document_id: UUID,
        run_id: UUID | None = Field(default=None),
        name: str = Field(default="review", pattern=r"^[A-Za-z0-9_-]{1,64}$"),
        width: int | None = Field(default=None, ge=320, le=4096),
        height: int | None = Field(default=None, ge=240, le=4096),
        zoom: Literal["unchanged", "extents"] = Field(default="extents"),
    ) -> SnapshotResult:
        request = CaptureViewRequest(
            operation_id=operation_id,
            document_id=document_id,
            run_id=run_id,
            name=name,
            width=width,
            height=height,
            zoom=zoom,
        )
        state = get_state(ctx)
        check_permission(state.config.server.permission_profile, "cad.view.capture")

        async def execute():
            return await _capture_view_core(state, request)

        return await with_idempotency(
            state,
            tool_name="gcad_capture_view",
            operation_id=request.operation_id,
            document_id=request.document_id,
            arguments=request.model_dump(mode="json"),
            result_model=SnapshotResult.model_validate,
            execute=execute,
        )

    @mcp.tool(
        name="gcad_begin_run",
        title="Begin an evidence run",
        description=(
            "Start an auditable drawing run: creates the run directory, manifest, and brief. "
            "Idempotent by operation_id."
        ),
        annotations=MUTATING,
        structured_output=True,
    )
    async def gcad_begin_run(
        ctx: Context[AppContext],
        operation_id: UUID,
        title: str = Field(min_length=1, max_length=500),
        intent: str = Field(min_length=1, max_length=20_000),
        document_id: UUID | None = Field(default=None),
        units: str = Field(default="mm", max_length=32),
        assumptions: list[str] = Field(default_factory=list, max_length=100),
        expected_outputs: list[str] = Field(default_factory=list, max_length=50),
    ) -> BeginRunResult:
        request = BeginRunRequest(
            operation_id=operation_id,
            title=title,
            intent=intent,
            document_id=document_id,
            units=units,
            assumptions=assumptions,
            expected_outputs=expected_outputs,
        )
        state = get_state(ctx)
        check_permission(state.config.server.permission_profile, "cad.run.manage")
        run_id = uuid4()
        now = utc_now()
        manifest = RunManifest(
            run_id=run_id,
            runtime_id=state.runtime_id,
            status=RunStatus.RUNNING,
            title=request.title,
            intent=request.intent,
            units=request.units,
            assumptions=request.assumptions,
            document_id=request.document_id,
            created_at=now,
            updated_at=now,
            last_operation_id=request.operation_id,
        )

        async def execute():
            state.run_store.create_run(manifest)
            brief = [
                f"# {request.title}",
                "",
                "## Intent",
                request.intent,
                "",
                f"- Units: {request.units}",
            ]
            if request.assumptions:
                brief.append("- Assumptions:")
                brief.extend(f"  - {a}" for a in request.assumptions)
            if request.expected_outputs:
                brief.append("- Expected outputs:")
                brief.extend(f"  - {o}" for o in request.expected_outputs)
            state.run_store.write_brief(run_id, "\n".join(brief) + "\n")
            state.audit.record("cad.run.begin", run_id=str(run_id), title=request.title)
            return BeginRunResult(
                run_id=run_id,
                runtime_id=state.runtime_id,
                status=RunStatus.RUNNING,
                manifest_uri=f"gcad://runs/{run_id}/manifest",
                document_id=request.document_id,
            )

        return await with_idempotency(
            state,
            tool_name="gcad_begin_run",
            operation_id=request.operation_id,
            document_id=request.document_id,
            arguments=request.model_dump(mode="json"),
            result_model=BeginRunResult.model_validate,
            execute=execute,
        )

    @mcp.tool(
        name="gcad_capture_before_state",
        title="Capture before-state evidence",
        description=(
            "Persist the initial structural entity inventory (and optional 'before' screenshot) "
            "for a run. Idempotent unless replace=true."
        ),
        annotations=MUTATING,
        structured_output=True,
    )
    async def gcad_capture_before_state(
        ctx: Context[AppContext],
        operation_id: UUID,
        run_id: UUID,
        document_id: UUID,
        layout: str | None = Field(default=None, max_length=255),
        screenshot: bool = Field(default=True),
        replace: bool = Field(default=False),
    ) -> EvidenceResult:
        request = CaptureBeforeStateRequest(
            operation_id=operation_id,
            run_id=run_id,
            document_id=document_id,
            layout=layout,
            screenshot=screenshot,
            replace=replace,
        )
        state = get_state(ctx)
        check_permission(state.config.server.permission_profile, "cad.run.manage")

        async def execute():
            run_dir = state.run_store.run_dir(request.run_id)
            before_path = run_dir / "before_entities.json"
            artifacts: dict[str, str] = {}
            if before_path.exists() and not request.replace:
                inventory = json.loads(before_path.read_text(encoding="utf-8"))
            else:
                inventory = await run_command(
                    state,
                    CadCommand(
                        name="capture_inventory",
                        document_id=request.document_id,
                        run_id=request.run_id,
                        payload={"layout": request.layout},
                    ),
                )
                before_path.write_text(
                    json.dumps(inventory, indent=2, sort_keys=True), encoding="utf-8"
                )
            artifacts["before-entities"] = f"gcad://runs/{request.run_id}/before-entities"
            if request.screenshot:
                snap = await _capture_view_core(
                    state,
                    CaptureViewRequest(
                        operation_id=uuid4(),
                        document_id=request.document_id,
                        run_id=request.run_id,
                        name="before",
                        width=None,
                        height=None,
                    ),
                )
                artifacts["snapshot-before"] = snap.resource_uri
            manifest = state.run_store.read_manifest(request.run_id)
            manifest.artifacts.update(artifacts)
            manifest.last_operation_id = request.operation_id
            state.run_store.write_manifest(manifest)
            return EvidenceResult(
                run_id=request.run_id,
                document_id=request.document_id,
                artifacts=artifacts,
                entity_count=inventory.get("count", 0),
            )

        try:
            return await with_idempotency(
                state,
                tool_name="gcad_capture_before_state",
                operation_id=request.operation_id,
                document_id=request.document_id,
                arguments=request.model_dump(mode="json"),
                result_model=EvidenceResult.model_validate,
                execute=execute,
            )
        except ExpectedCadError as exc:
            raise map_error(exc) from exc

    @mcp.tool(
        name="gcad_collect_evidence",
        title="Collect after-state evidence",
        description=(
            "Collect the current entity inventory, document summary, and a review screenshot "
            "for a run."
        ),
        annotations=MUTATING,
        structured_output=True,
    )
    async def gcad_collect_evidence(
        ctx: Context[AppContext],
        operation_id: UUID,
        run_id: UUID,
        document_id: UUID,
        layout: str | None = Field(default=None, max_length=255),
        screenshot: bool = Field(default=True),
    ) -> EvidenceResult:
        request = CollectEvidenceRequest(
            operation_id=operation_id,
            run_id=run_id,
            document_id=document_id,
            layout=layout,
            screenshot=screenshot,
        )
        state = get_state(ctx)
        check_permission(state.config.server.permission_profile, "cad.run.manage")

        async def execute():
            run_dir = state.run_store.run_dir(request.run_id)
            inventory = await run_command(
                state,
                CadCommand(
                    name="capture_inventory",
                    document_id=request.document_id,
                    run_id=request.run_id,
                    payload={"layout": request.layout},
                ),
            )
            (run_dir / "after_entities.json").write_text(
                json.dumps(inventory, indent=2, sort_keys=True), encoding="utf-8"
            )
            docs = await run_command(state, CadCommand(name="list_documents", payload={}))
            summary = next(
                (d for d in docs["documents"] if d["document_id"] == str(request.document_id)),
                None,
            )
            (run_dir / "document_summary.json").write_text(
                json.dumps(summary or {}, indent=2, sort_keys=True), encoding="utf-8"
            )
            artifacts = {
                "after-entities": f"gcad://runs/{request.run_id}/after-entities",
            }
            if request.screenshot:
                snap = await _capture_view_core(
                    state,
                    CaptureViewRequest(
                        operation_id=uuid4(),
                        document_id=request.document_id,
                        run_id=request.run_id,
                        name="review",
                    ),
                )
                artifacts["snapshot-review"] = snap.resource_uri
            manifest = state.run_store.read_manifest(request.run_id)
            manifest.artifacts.update(artifacts)
            manifest.last_operation_id = request.operation_id
            state.run_store.write_manifest(manifest)
            return EvidenceResult(
                run_id=request.run_id,
                document_id=request.document_id,
                artifacts=artifacts,
                entity_count=inventory.get("count", 0),
            )

        try:
            return await with_idempotency(
                state,
                tool_name="gcad_collect_evidence",
                operation_id=request.operation_id,
                document_id=request.document_id,
                arguments=request.model_dump(mode="json"),
                result_model=EvidenceResult.model_validate,
                execute=execute,
            )
        except ExpectedCadError as exc:
            raise map_error(exc) from exc

    @mcp.tool(
        name="gcad_validate_run",
        title="Validate run evidence",
        description=(
            "Run deterministic structural validation against the run's evidence (inventories, "
            "screenshot, save state, journal). Does not claim semantic visual correctness."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
        ),
        structured_output=True,
    )
    async def gcad_validate_run(
        ctx: Context[AppContext],
        operation_id: UUID,
        run_id: UUID,
        document_id: UUID | None = Field(default=None),
    ) -> ValidateRunResult:
        request = ValidateRunRequest(
            operation_id=operation_id, run_id=run_id, document_id=document_id
        )
        state = get_state(ctx)
        check_permission(state.config.server.permission_profile, "cad.run.manage")
        try:
            run_dir = state.run_store.run_dir(request.run_id)
            manifest = state.run_store.read_manifest(request.run_id)
            after_path = run_dir / "after_entities.json"
            after_inventory = (
                json.loads(after_path.read_text(encoding="utf-8")) if after_path.exists() else None
            )
            screenshot_path = state.run_store.snapshot_path(request.run_id, "review")
            output_dwg = None
            outputs = list((run_dir / "outputs").glob("*.dwg"))
            if outputs:
                output_dwg = outputs[0]
            checks = validate_run(
                run_dir=run_dir,
                manifest=manifest,
                after_inventory=after_inventory,
                screenshot_path=screenshot_path if screenshot_path.exists() else None,
                output_dwg_path=output_dwg,
                saved_after_last_mutation=None,
                had_partial_commit=False,
                screenshot_expected=state.config.evidence.require_screenshot_for_success,
            )
            (run_dir / "validation.json").write_text(
                json.dumps([c.model_dump(mode="json") for c in checks], indent=2),
                encoding="utf-8",
            )
            failed = [c for c in checks if c.status == "failed"]
            overall = "passed" if not failed else ("warning" if not checks else "failed")
            overall = "passed" if not failed else "failed"
            return ValidateRunResult(run_id=request.run_id, checks=checks, overall=overall)
        except ExpectedCadError as exc:
            raise map_error(exc) from exc

    @mcp.tool(
        name="gcad_finalize_run",
        title="Finalize a run",
        description=(
            "Save the deliverable, capture final evidence, validate, and write the final "
            "manifest/feedback. Missing evidence yields partial, never full success. Idempotent "
            "by operation_id."
        ),
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False
        ),
        structured_output=True,
    )
    async def gcad_finalize_run(
        ctx: Context[AppContext],
        operation_id: UUID,
        run_id: UUID,
        document_id: UUID | None = Field(default=None),
        output_relative_path: str | None = Field(default=None, max_length=1024),
        overwrite: bool = Field(default=False),
        screenshot_name: str = Field(default="final", pattern=r"^[A-Za-z0-9_-]{1,64}$"),
    ) -> FinalizeRunResult:
        request = FinalizeRunRequest(
            operation_id=operation_id,
            run_id=run_id,
            document_id=document_id,
            output_relative_path=output_relative_path,
            overwrite=overwrite,
            screenshot_name=screenshot_name,
        )
        state = get_state(ctx)
        check_permission(state.config.server.permission_profile, "cad.run.manage")

        async def execute():
            run_dir = state.run_store.run_dir(request.run_id)
            manifest = state.run_store.read_manifest(request.run_id)
            warnings: list[str] = []
            document_id = request.document_id or manifest.document_id
            saved_relative = None
            if document_id is not None:
                # Capture the final view before saving: on some GstarCAD versions
                # (e.g. 2026) the view change re-marks the document dirty, and the
                # save must be the last mutation for saved_after_mutation to hold.
                await _capture_view_core(
                    state,
                    CaptureViewRequest(
                        operation_id=uuid4(),
                        document_id=document_id,
                        run_id=request.run_id,
                        name=request.screenshot_name,
                    ),
                )
            if document_id is not None and request.output_relative_path:
                resolved = state.workspace.resolve_output(
                    request.output_relative_path, overwrite=request.overwrite
                )
                await run_command(
                    state,
                    CadCommand(
                        name="save_document",
                        document_id=document_id,
                        payload={
                            "mode": "save_as",
                            "output_path": str(resolved),
                            "relative_path": request.output_relative_path,
                        },
                    ),
                )
                saved_relative = request.output_relative_path
                output_copy = run_dir / "outputs" / Path(request.output_relative_path).name
                if resolved.exists():
                    output_copy.write_bytes(resolved.read_bytes())
                manifest.artifacts["output-dwg"] = (
                    f"outputs/{Path(request.output_relative_path).name}"
                )
            if document_id is not None:
                after_inventory = await run_command(
                    state,
                    CadCommand(
                        name="capture_inventory",
                        document_id=document_id,
                        run_id=request.run_id,
                        payload={},
                    ),
                )
                (run_dir / "after_entities.json").write_text(
                    json.dumps(after_inventory, indent=2, sort_keys=True), encoding="utf-8"
                )
            else:
                warnings.append("No document associated; screenshot/after-inventory skipped.")
                after_inventory = None

            screenshot_path = state.run_store.snapshot_path(request.run_id, request.screenshot_name)
            outputs = list((run_dir / "outputs").glob("*.dwg"))
            checks = validate_run(
                run_dir=run_dir,
                manifest=manifest,
                after_inventory=after_inventory,
                screenshot_path=screenshot_path if screenshot_path.exists() else None,
                output_dwg_path=outputs[0] if outputs else None,
                saved_after_last_mutation=bool(saved_relative),
                had_partial_commit=False,
                screenshot_expected=state.config.evidence.require_screenshot_for_success,
            )
            (run_dir / "validation.json").write_text(
                json.dumps([c.model_dump(mode="json") for c in checks], indent=2), encoding="utf-8"
            )
            failed = [c for c in checks if c.status == "failed"]
            has_useful_output = outputs or (after_inventory or {}).get("count", 0) > 0
            if not failed:
                status = RunStatus.SUCCEEDED
            elif has_useful_output:
                status = RunStatus.PARTIAL
            else:
                status = RunStatus.FAILED
            manifest.status = status
            manifest.validations = checks
            manifest.warnings = warnings
            manifest.last_operation_id = request.operation_id
            if saved_relative:
                manifest.artifacts["saved-path"] = saved_relative
            state.run_store.write_manifest(manifest)
            feedback = [
                f"# Feedback — {manifest.title}",
                "",
                f"- Status: {status.value}",
                f"- Checks: {len(checks) - len(failed)} passed / {len(failed)} failed",
            ]
            for check in failed:
                feedback.append(f"- FAILED {check.check_id}: {check.message}")
            if warnings:
                feedback.extend(f"- Warning: {w}" for w in warnings)
            state.run_store.write_artifact(
                request.run_id, "feedback.md", "\n".join(feedback) + "\n"
            )
            state.audit.record("cad.run.finalize", run_id=str(request.run_id), status=status.value)
            return FinalizeRunResult(
                run_id=request.run_id,
                status=status,
                manifest_uri=f"gcad://runs/{request.run_id}/manifest",
                artifacts=manifest.artifacts,
                checks=checks,
                warnings=warnings,
            )

        try:
            return await with_idempotency(
                state,
                tool_name="gcad_finalize_run",
                operation_id=request.operation_id,
                document_id=request.document_id,
                arguments=request.model_dump(mode="json"),
                result_model=FinalizeRunResult.model_validate,
                execute=execute,
            )
        except ExpectedCadError as exc:
            raise map_error(exc) from exc

    @mcp.tool(
        name="gcad_get_run_status",
        title="Run status",
        description="Return current run state and artifact links without mutation.",
        annotations=ToolAnnotations(
            read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
        ),
        structured_output=True,
    )
    async def gcad_get_run_status(
        ctx: Context[AppContext],
        run_id: UUID,
    ) -> RunStatusResult:
        request = RunStatusRequest(run_id=run_id)
        state = get_state(ctx)
        check_permission(state.config.server.permission_profile, "cad.run.manage")
        try:
            manifest = state.run_store.read_manifest(request.run_id)
        except ExpectedCadError as exc:
            raise map_error(exc) from exc
        return RunStatusResult(
            run_id=request.run_id,
            status=manifest.status,
            title=manifest.title,
            artifacts=manifest.artifacts,
        )
