"""End-to-end smoke over real stdio: launch `gstarcad-mcp serve`, render the
create-2d-drawing prompt, and execute that prompt's workflow against live GstarCAD."""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

WORKSPACE = Path(__file__).resolve().parents[1] / "smoke_workspace"

REQUIREMENT = (
    "A 100 x 60 mm rectangular plate with a center hole radius 10 mm and four "
    "corner mounting holes radius 3 mm at (10,10), (90,10), (10,50), (90,50)."
)


def header(title: str) -> None:
    print(f"\n=== {title} ===", flush=True)


async def call(session: ClientSession, tool: str, **arguments) -> dict:
    result = await session.call_tool(tool, arguments)
    if result.is_error:
        text = result.content[0].text if result.content else "(no content)"
        raise SystemExit(f"{tool} failed: {text}")
    return result.structured_content


async def main() -> int:
    server_exe = Path(sys.executable).parent / "gstarcad-mcp.exe"
    env = os.environ.copy()
    env["GSTARCAD_MCP_WORKSPACE_ROOT"] = str(WORKSPACE)
    params = StdioServerParameters(command=str(server_exe), args=["serve"], env=env)

    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        header("tools")
        tools = await session.list_tools()
        print(len(tools.tools), "tools:", ", ".join(t.name for t in tools.tools))

        header("prompts")
        prompts = await session.list_prompts()
        for p in prompts.prompts:
            print("-", p.name, "|", (p.description or "")[:70])

        header("resources")
        resources = await session.list_resources()
        templates = await session.list_resource_templates()
        print(
            len(resources.resources),
            "static resources;",
            len(templates.resource_templates),
            "templates:",
            ", ".join(t.uri_template for t in templates.resource_templates),
        )

        header("prompt: gcad_create_2d_drawing")
        prompt = await session.get_prompt("gcad_create_2d_drawing", {"requirement": REQUIREMENT})
        text = prompt.messages[0].content.text
        print(text[:700], "\n..." if len(text) > 700 else "")

        header("workflow (following the prompt)")
        status = await call(session, "gcad_get_status")
        print(
            "runtime_state:",
            status["runtime_state"],
            "| profile:",
            status["permission_profile"],
            "| connected:",
            status["connected"],
        )

        run = await call(
            session,
            "gcad_begin_run",
            operation_id=uuid.uuid4(),
            title="Smoke: mounting plate",
            intent=REQUIREMENT,
            units="mm",
        )
        run_id = run["run_id"]
        print("run:", run_id)

        doc = await call(session, "gcad_new_document", operation_id=uuid.uuid4())
        document_id = doc["document"]["document_id"]
        print("document:", document_id)

        await call(
            session,
            "gcad_capture_before_state",
            operation_id=uuid.uuid4(),
            run_id=run_id,
            document_id=document_id,
        )
        print("before state captured")

        batch = await call(
            session,
            "gcad_apply_actions",
            operation_id=uuid.uuid4(),
            document_id=document_id,
            run_id=run_id,
            actions=[
                {"op": "ensure_layer", "name": "PLATE", "color": 7},
                {"op": "ensure_layer", "name": "HOLES", "color": 1},
                {
                    "op": "create_rect",
                    "corner1": [0, 0],
                    "corner2": [100, 60],
                    "layer": "PLATE",
                },
                {"op": "create_circle", "center": [50, 30], "radius": 10.0, "layer": "HOLES"},
                *[
                    {"op": "create_circle", "center": c, "radius": 3.0, "layer": "HOLES"}
                    for c in ([10, 10], [90, 10], [10, 50], [90, 50])
                ],
            ],
        )
        print(
            "batch:",
            batch["status"],
            "| transaction_mode:",
            batch["transaction_mode"],
            "| actions:",
            len(batch["actions"]),
        )

        page = await call(session, "gcad_query_entities", document_id=document_id)
        print("entities in model space:", len(page["entities"]))

        shot = await call(
            session,
            "gcad_capture_view",
            operation_id=uuid.uuid4(),
            document_id=document_id,
            run_id=run_id,
            name="review",
        )
        print(
            "screenshot:",
            shot["relative_path"],
            "| bytes:",
            shot["byte_size"],
            "| uniform:",
            shot["uniform"],
        )

        fin = await call(
            session,
            "gcad_finalize_run",
            operation_id=uuid.uuid4(),
            run_id=run_id,
            document_id=document_id,
            output_relative_path=f"outputs/plate_smoke_{uuid.uuid4().hex[:8]}.dwg",
        )
        print("finalize status:", fin["status"])
        for check in fin["checks"]:
            print("  check:", check["check_id"], "->", check["status"])
        for name, uri in fin["artifacts"].items():
            print("  artifact:", name, "->", uri)

        header("evidence resources")
        manifest = await session.read_resource(f"gcad://runs/{run_id}/manifest")
        print("manifest head:", manifest.contents[0].text[:260].replace("\n", " "), "...")
        png = await session.read_resource(f"gcad://runs/{run_id}/snapshots/review")
        blob = png.contents[0]
        data = getattr(blob, "blob", None) or blob.text.encode()
        print("review.png via resource:", len(data), "bytes")

        header("cleanup")
        await call(
            session,
            "gcad_close_document",
            operation_id=uuid.uuid4(),
            document_id=document_id,
            save_policy="reject_dirty",
        )
        print("document closed; smoke test complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
