# Host configuration

Examples live in `examples/`:

- `claude_desktop_config.json` — production-style install (`gstarcad-mcp serve`)
- `claude_desktop_config.dev.json` — development launch via `uv`
- `codex_config.toml` — Codex CLI `[mcp_servers.gstarcad]`
- `vscode_mcp.json` — VS Code MCP servers file

Generic form:

```json
{
  "command": "gstarcad-mcp",
  "args": ["serve"],
  "env": {
    "GSTARCAD_MCP_CONFIG": "C:\\Users\\USER\\.config\\gstarcad-mcp\\server.toml"
  }
}
```

## Launch notes

- Host-launched processes may not inherit your shell environment; use
  absolute executable and config paths in production.
- Server logs go to stderr and the rotating file under
  `workspace/logs/` — never stdout (stdout is the protocol transport).
- GstarCAD must run in the same interactive user session as the server.
- Do not run two server processes against one GstarCAD instance.

## GstarCAD version selection

With the default `prog_id = "auto"` the server discovers every registered
GstarCAD COM ProgID (e.g. `GStarCAD.Application.27` for 2027,
`GStarCAD.Application.26` for 2026), newest version first, and attaches to a
running instance or launches one through the first working ProgID. Multiple
installed versions are therefore supported out of the box.

To pin one version, set an explicit ProgID:

```toml
[cad]
prog_id = "GStarCAD.Application.26"
```

or `GSTARCAD_MCP_PROG_ID=GStarCAD.Application.26` in the server environment.
`gcad_get_status` reports the ProgID actually connected (`connected_prog_id`).

## Verification

After configuring a host:

1. Ask the model to call `gcad_get_status` — it must report runtime state
   even when GstarCAD is unavailable.
2. Ask it to list documents (`gcad_list_documents`).
3. Optionally run MCP Inspector:

```powershell
npx @modelcontextprotocol/inspector --cli uv run gstarcad-mcp serve --method tools/list
```
