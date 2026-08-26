"""Full-coverage live test over real stdio.

Exercises every tool, every action op, all six prompts, every resource kind,
idempotent replay, error paths, and the readonly permission profile against
a real GstarCAD session.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

WORKSPACE = Path(__file__).resolve().parents[1] / "fullcoverage_workspace"
PASSED: list[str] = []


def header(title: str) -> None:
    print(f"\n=== {title} ===", flush=True)


def ok(label: str) -> None:
    PASSED.append(label)
    print("  ok:", label, flush=True)


async def call(session: ClientSession, tool: str, **arguments) -> dict:
    result = await session.call_tool(tool, arguments)
    if result.is_error:
        text = result.content[0].text if result.content else "(no content)"
        raise SystemExit(f"FAIL {tool}: {text}")
    return result.structured_content


async def call_error(session: ClientSession, tool: str, **arguments) -> str:
    result = await session.call_tool(tool, arguments)
    if not result.is_error:
        raise SystemExit(f"FAIL {tool}: expected an error, got success")
    return result.content[0].text if result.content else ""


def server_params(**extra_env) -> StdioServerParameters:
    env = os.environ.copy()
    env["GSTARCAD_MCP_WORKSPACE_ROOT"] = str(WORKSPACE)
    env.update(extra_env)
    exe = Path(sys.executable).parent / "gstarcad-mcp.exe"
    return StdioServerParameters(command=str(exe), args=["serve"], env=env)


PROMPT_ARGS = {
    "gcad_create_2d_drawing": {"requirement": "A 100x60 plate with holes."},
    "gcad_modify_existing_drawing": {"requirement": "Enlarge the center hole to R12."},
    "gcad_mechanical_three_view": {"requirement": "A stepped shaft, 80 mm long, three views."},
    "gcad_review_and_repair": {"requirement": "Screenshot came out blank; review and repair."},
    "gcad_finalize_with_evidence": {},
    "gcad_validate_before_delivery": {},
}

SWEEP_ACTIONS = [
    {"op": "create_segment", "start": [0, 0], "end": [40, 0], "layer": "GEOM"},
    {"op": "create_circle", "center": [60, 20], "radius": 8.0, "layer": "GEOM"},
    {
        "op": "create_arc",
        "center": [90, 20],
        "radius": 10.0,
        "start_angle": 0.0,
        "end_angle": 3.14159,
        "layer": "GEOM",
    },
    {
        "op": "create_ellipse",
        "center": [120, 20],
        "semi_major": 15.0,
        "semi_minor": 7.0,
        "layer": "GEOM",
    },
    {
        "op": "create_polyline",
        "closed": True,
        "layer": "GEOM",
        "vertices": [[0, 40], [30, 40], [30, 60], [0, 60]],
    },
    {"op": "create_rect", "corner1": [50, 40], "corner2": [80, 60], "layer": "GEOM"},
    {
        "op": "create_text",
        "position": [0, 70],
        "height": 5.0,
        "text": "FULL COVERAGE SWEEP",
        "layer": "ANNO",
    },
    {
        "op": "create_hatch",
        "pattern_name": "SOLID",
        "scale": 1.0,
        "layer": "GEOM",
        "boundary_points": [[50, 40], [80, 40], [80, 60], [50, 60]],
    },
    {
        "op": "create_dimension",
        "pt1": [0, 0],
        "pt2": [40, 0],
        "dim_line_pt": [20, -10],
        "layer": "ANNO",
    },
    {
        "op": "create_table",
        "position": [100, 40],
        "title": "BOM",
        "data": [{"cells": ["Part", "Qty"]}, {"cells": ["Plate", "1"]}],
        "layer": "ANNO",
    },
    {"op": "regen"},
    {"op": "zoom_extents"},
]


async def run_full_coverage(session: ClientSession) -> None:
    header("discovery")
    tools = await session.list_tools()
    assert len(tools.tools) == 21, len(tools.tools)
    ok(f"list_tools -> {len(tools.tools)} tools")
    prompts = await session.list_prompts()
    assert {p.name for p in prompts.prompts} == set(PROMPT_ARGS)
    ok(f"list_prompts -> {len(prompts.prompts)} prompts")
    templates = await session.list_resource_templates()
    resources = await session.list_resources()
    ok(
        f"resources: {len(resources.resources)} static, "
        f"{len(templates.resource_templates)} templates"
    )

    header("prompts render")
    for name, args in PROMPT_ARGS.items():
        prompt = await session.get_prompt(name, args)
        assert prompt.messages and prompt.messages[0].content.text
        ok(f"prompt {name} ({len(prompt.messages[0].content.text)} chars)")

    header("status + document registry")
    status = await call(session, "gcad_get_status")
    assert status["runtime_state"] == "ready"
    ok(f"gcad_get_status runtime_state={status['runtime_state']} docs={status['document_count']}")

    doc_a = (await call(session, "gcad_new_document", operation_id=uuid.uuid4()))["document"][
        "document_id"
    ]
    doc_b = (await call(session, "gcad_new_document", operation_id=uuid.uuid4()))["document"][
        "document_id"
    ]
    docs = await call(session, "gcad_list_documents")
    ids = {d["document_id"] for d in docs["documents"]}
    assert doc_a in ids and doc_b in ids
    ok(f"gcad_new_document x2 + gcad_list_documents ({len(docs['documents'])} docs)")

    act = await call(session, "gcad_activate_document", document_id=doc_a)
    assert act["document"]["active"] is True
    ok("gcad_activate_document")

    header("layers: ensure + idempotent replay + conflict")
    layers_op = uuid.uuid4()
    r1 = await call(
        session,
        "gcad_ensure_layers",
        operation_id=layers_op,
        document_id=doc_a,
        layers=[{"name": "GEOM", "color": 7}, {"name": "ANNO", "color": 2}],
    )
    r2 = await call(
        session,
        "gcad_ensure_layers",
        operation_id=layers_op,
        document_id=doc_a,
        layers=[{"name": "GEOM", "color": 7}, {"name": "ANNO", "color": 2}],
    )
    assert r1["revision_after"] == r2["revision_after"]
    ok("gcad_ensure_layers + same-operation replay returns stored result")

    conflict = await call_error(
        session,
        "gcad_ensure_layers",
        operation_id=layers_op,
        document_id=doc_a,
        layers=[{"name": "OTHER"}],
    )
    assert "IDEMPOTENCY_CONFLICT" in conflict, conflict
    ok("same operation_id with different args -> IDEMPOTENCY_CONFLICT")

    layers = await call(session, "gcad_list_layers", document_id=doc_a)
    names = {layer["name"] for layer in layers["layers"]}
    assert {"GEOM", "ANNO"} <= names
    ok(f"gcad_list_layers ({sorted(names)})")

    header("entity sweep: all ops via create_entities + apply_actions")
    sweep = await call(
        session,
        "gcad_create_entities",
        operation_id=uuid.uuid4(),
        document_id=doc_a,
        entities=SWEEP_ACTIONS[:10],
    )
    assert sweep["status"] == "succeeded", sweep
    ok(f"gcad_create_entities 10 ops -> {sweep['status']}")

    tail = await call(
        session,
        "gcad_apply_actions",
        operation_id=uuid.uuid4(),
        document_id=doc_a,
        actions=SWEEP_ACTIONS[10:],
    )
    assert tail["status"] == "succeeded"
    ok(f"gcad_apply_actions regen+zoom -> {tail['status']}")

    header("inspection")
    layouts = await call(session, "gcad_list_layouts", document_id=doc_a)
    ok(f"gcad_list_layouts -> {[layout['name'] for layout in layouts['layouts']]}")

    page1 = await call(session, "gcad_query_entities", document_id=doc_a, limit=3)
    assert len(page1["entities"]) == 3 and page1["next_cursor"]
    page2 = await call(
        session,
        "gcad_query_entities",
        document_id=doc_a,
        limit=100,
        cursor=page1["next_cursor"],
    )
    total = 3 + len(page2["entities"])
    ok(f"gcad_query_entities paginated (3 + {len(page2['entities'])} = {total})")

    filtered = await call(
        session,
        "gcad_query_entities",
        document_id=doc_a,
        layers=["ANNO"],
        limit=100,
    )
    ok(f"gcad_query_entities layer filter -> {len(filtered['entities'])}")

    handles = [e["handle"] for e in page1["entities"]][:2]
    got = await call(session, "gcad_get_entities", document_id=doc_a, handles=handles)
    assert len(got["entities"]) == len(handles)
    ok("gcad_get_entities by handle")
    missing = await call(session, "gcad_get_entities", document_id=doc_a, handles=["ZZZZZZ"])
    assert missing["missing_handles"] == ["ZZZZZZ"]
    ok("gcad_get_entities reports missing handles")

    header("run lifecycle + evidence")
    run = await call(
        session,
        "gcad_begin_run",
        operation_id=uuid.uuid4(),
        title="Full coverage run",
        intent="Exercise every tool.",
        document_id=doc_a,
        units="mm",
    )
    run_id = run["run_id"]
    ok(f"gcad_begin_run -> {run_id}")
    await call(
        session,
        "gcad_capture_before_state",
        operation_id=uuid.uuid4(),
        run_id=run_id,
        document_id=doc_a,
    )
    ok("gcad_capture_before_state")
    await call(
        session,
        "gcad_apply_actions",
        operation_id=uuid.uuid4(),
        document_id=doc_a,
        run_id=run_id,
        actions=[{"op": "create_circle", "center": [150, 80], "radius": 5.0, "layer": "GEOM"}],
    )
    ev = await call(
        session,
        "gcad_collect_evidence",
        operation_id=uuid.uuid4(),
        run_id=run_id,
        document_id=doc_a,
    )
    ok(f"gcad_collect_evidence ({ev['entity_count']} entities)")
    validation = await call(
        session,
        "gcad_validate_run",
        operation_id=uuid.uuid4(),
        run_id=run_id,
        document_id=doc_a,
    )
    ok(f"gcad_validate_run overall={validation['overall']}")
    run_status = await call(session, "gcad_get_run_status", run_id=run_id)
    ok(f"gcad_get_run_status -> {run_status['status']}")

    header("save / finalize / close")
    shot = await call(
        session,
        "gcad_capture_view",
        operation_id=uuid.uuid4(),
        document_id=doc_a,
        name="latest",
    )
    ok(f"gcad_capture_view without run -> {shot['relative_path']}")
    fin = await call(
        session,
        "gcad_finalize_run",
        operation_id=uuid.uuid4(),
        run_id=run_id,
        document_id=doc_a,
        output_relative_path=f"outputs/full_coverage_{uuid.uuid4().hex[:8]}.dwg",
    )
    assert fin["status"] == "succeeded", fin
    ok(f"gcad_finalize_run -> {fin['status']} ({len(fin['checks'])} checks)")

    for suffix in ("summary", "layers", "layouts"):
        content = (
            (await session.read_resource(f"gcad://documents/{doc_a}/{suffix}")).contents[0].text
        )
        assert content
        ok(f"read document {suffix}")
    entity = (
        (await session.read_resource(f"gcad://documents/{doc_a}/entities/{handles[0]}"))
        .contents[0]
        .text
    )
    assert handles[0] in entity
    ok("read entity resource")
    snap = await session.read_resource(f"gcad://documents/{doc_a}/snapshot/latest")
    blob = getattr(snap.contents[0], "blob", None) or snap.contents[0].text.encode()
    ok(f"read document snapshot/latest ({len(blob)} bytes)")

    await call(
        session,
        "gcad_close_document",
        operation_id=uuid.uuid4(),
        document_id=doc_a,
        save_policy="discard",
    )
    ok("gcad_close_document (discard doc_a after save_as)")
    await call(
        session,
        "gcad_close_document",
        operation_id=uuid.uuid4(),
        document_id=doc_b,
        save_policy="discard",
    )
    ok("gcad_close_document (discard doc_b)")

    header("resources")
    for uri in ("gcad://status", "gcad://documents"):
        content = (await session.read_resource(uri)).contents[0].text
        assert content
        ok(f"read {uri}")
    for artifact in (
        "manifest",
        "brief",
        "actions",
        "before-entities",
        "after-entities",
        "feedback",
        "validation",
    ):
        content = (await session.read_resource(f"gcad://runs/{run_id}/{artifact}")).contents[0].text
        assert content
        ok(f"read run {artifact}")
    png = await session.read_resource(f"gcad://runs/{run_id}/snapshots/review")
    content = png.contents[0]
    blob = getattr(content, "blob", None) or getattr(content, "text", "").encode()
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        import base64

        blob = base64.b64decode(blob)
    assert blob[:8] == b"\x89PNG\r\n\x1a\n"
    ok(f"read run snapshot ({len(blob)} bytes, PNG signature valid)")

    reopened = await call(
        session,
        "gcad_open_document",
        operation_id=uuid.uuid4(),
        path=fin["artifacts"]["output-dwg"],
    )
    persisted = await call(
        session,
        "gcad_query_entities",
        document_id=reopened["document"]["document_id"],
        limit=100,
    )
    assert len(persisted["entities"]) >= total
    ok(f"gcad_open_document reopened output ({len(persisted['entities'])} entities persisted)")
    await call(
        session,
        "gcad_save_document",
        operation_id=uuid.uuid4(),
        document_id=reopened["document"]["document_id"],
        mode="save",
    )
    ok("gcad_save_document in place")
    await call(
        session,
        "gcad_close_document",
        operation_id=uuid.uuid4(),
        document_id=reopened["document"]["document_id"],
        save_policy="reject_dirty",
    )

    header("error paths")
    err = await call_error(session, "gcad_query_entities", document_id=uuid.uuid4())
    assert "DOCUMENT_NOT_FOUND" in err, err
    ok("unknown document -> DOCUMENT_NOT_FOUND")
    err = await call_error(
        session,
        "gcad_open_document",
        operation_id=uuid.uuid4(),
        path="..\\..\\Windows\\System32\\evil.dwg",
    )
    assert "PATH_DENIED" in err, err
    ok("hostile path -> PATH_DENIED")
    err = await call_error(session, "gcad_query_entities", document_id=doc_a, limit=1001)
    assert err
    ok("limit above schema cap rejected")
    try:
        await session.read_resource(f"gcad://runs/{uuid.uuid4()}/manifest")
        raise SystemExit("FAIL: missing run manifest should raise")
    except Exception as exc:
        assert "not found" in str(exc).lower(), exc
        ok("missing run resource -> not found")


async def run_readonly_profile() -> None:
    header("readonly permission profile (second server)")
    async with stdio_client(server_params(GSTARCAD_MCP_PERMISSION_PROFILE="readonly")) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            status = await call(session, "gcad_get_status")
            assert status["permission_profile"] == "readonly"
            ok("readonly server: gcad_get_status allowed")
            docs = await call(session, "gcad_list_documents")
            ok(f"readonly server: gcad_list_documents ({len(docs['documents'])} docs)")
            err = await call_error(session, "gcad_new_document", operation_id=uuid.uuid4())
            assert "denied" in err.lower() or "PERMISSION" in err, err
            ok("readonly server: mutation denied")


async def main() -> int:
    async with stdio_client(server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await run_full_coverage(session)
    await run_readonly_profile()
    header("summary")
    print(f"{len(PASSED)} checks passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
