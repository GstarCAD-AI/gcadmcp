# gstarcad-mcp-server (gcadmcp)

An [MCP](https://modelcontextprotocol.io) server for GstarCAD (GCAD). It lets MCP hosts (Codex, Claude Desktop, VS Code, opencode, …) inspect, create, modify, validate, and save GstarCAD drawings through typed, deterministic operations — with idempotency, revision checks, a workspace sandbox, permission profiles, and an auditable evidence contract.

All CAD capability comes from two sibling projects; this repo is the protocol, policy, and workflow runtime:

| Project | Role |
| --- | --- |
| [pygcadwin](../pygcadwin) | Python COM automation for GstarCAD. Typed operation registry + services (`0.2.x`). Never depends on MCP. |
| [gcadclaw](../gcadclaw) | Workflow/evidence contract packaged as `gcadclaw-assets`: prompts, workflows, JSON-schema contracts, evals. |

## Requirements

- Windows x64 with an **interactive desktop session**
- GstarCAD installed and registered as a COM server (`GStarCAD.Application.*`);
  verified against GstarCAD 2026 (`.26`) and 2027 (`.27`)
- Python 3.10–3.13 (`pywin32` on Windows)

Schema and MCP contract tests also run off-Windows; live CAD operations report `PLATFORM_UNSUPPORTED` there.

## Developer installation

```powershell
git clone https://github.com/GstarCAD-AI/pygcadwin.git
git clone https://github.com/GstarCAD-AI/gcadclaw.git
git clone https://github.com/GstarCAD-AI/gstarcad-mcp-server.git

cd gstarcad-mcp-server
uv sync --all-extras
uv run gstarcad-mcp validate-env
uv run gstarcad-mcp serve        # stdio MCP server; see scripts/run_inspector.ps1 for MCP Inspector
```

## Launcher scripts

`gstarcad-mcp.ps1` (Windows PowerShell) and `gstarcad-mcp.sh` (bash) wrap the common tasks so you don't need to remember the `uv` invocations:

```powershell
.\gstarcad-mcp.ps1 setup          # uv sync --all-extras
.\gstarcad-mcp.ps1 validate-env
.\gstarcad-mcp.ps1 serve          # stdio server (what MCP hosts run)
.\gstarcad-mcp.ps1 test           # fake-COM suite; add --live for real GstarCAD
.\gstarcad-mcp.ps1 smoke --full   # 55-check live smoke; --prog-id pins a GstarCAD version
.\gstarcad-mcp.ps1 help
```

The bash script exposes the same commands (`./gstarcad-mcp.sh …`); live CAD commands print a warning off-Windows.

## CLI

```powershell
gstarcad-mcp serve           # stdio MCP server (used by hosts)
gstarcad-mcp status          # quick diagnostic
gstarcad-mcp validate-env    # environment checks (--json for scripts)
gstarcad-mcp print-config    # effective non-secret configuration
gstarcad-mcp list-tools      # tool catalog without starting CAD
gstarcad-mcp version
```

## Tool surface (21 tools, `gcad_*`)

Status: `gcad_get_status`. Documents: `gcad_list_documents`, `gcad_new_document`, `gcad_open_document`, `gcad_activate_document`, `gcad_save_document`, `gcad_close_document`. Inspection: `gcad_list_layers`, `gcad_list_layouts`, `gcad_query_entities`, `gcad_get_entities`. Editing: `gcad_ensure_layers`, `gcad_create_entities`, `gcad_apply_actions`. Evidence/view: `gcad_capture_view`, `gcad_begin_run`, `gcad_capture_before_state`, `gcad_collect_evidence`, `gcad_validate_run`, `gcad_finalize_run`, `gcad_get_run_status`.

Host configuration examples are in `examples/`; operations/security/troubleshooting docs are in `docs/`; decision records are in `docs/adr/`; rendered prompt snapshots used by the smoke tests are in `docs/prompts/`.

## GstarCAD version selection

With the default `cad.prog_id = "auto"` the server discovers every registered GstarCAD COM ProgID, newest version first, and attaches to a running instance or launches one — so multiple installed versions (e.g. 2026 and 2027) work out of the box. Pin one version with `GSTARCAD_MCP_PROG_ID=GStarCAD.Application.26` or `[cad] prog_id` in the TOML config; `gcad_get_status` reports the connected ProgID. See `docs/host-configuration.md`.

## Canonical workflow

```text
gcad_get_status → gcad_begin_run → gcad_new_document/gcad_open_document
→ gcad_capture_before_state → gcad_apply_actions → gcad_query_entities
→ gcad_capture_view → visual review of the PNG → optional repair
→ gcad_collect_evidence → gcad_validate_run → gcad_finalize_run
```

## Testing

```powershell
uv run pytest tests -q                     # fake-COM unit + in-memory MCP contract tests
.\scripts\integration_test.ps1             # real Windows/GstarCAD pytest suite (serial)

# Live end-to-end smokes over real stdio against a running/launched GstarCAD:
uv run python scripts/smoke_full.py        # 55 checks: every tool/op/prompt/resource/error path
uv run python scripts/smoke_mcp.py         # prompt-driven drawing workflow with evidence

# Target a specific GstarCAD version for either smoke:
$env:GSTARCAD_MCP_PROG_ID = "GStarCAD.Application.26"   # or .27
```

`.ps1` integration runs and the live smokes need one interactive desktop GstarCAD; never run multiple workers against one instance.

## License

MIT, matching the sibling projects.
