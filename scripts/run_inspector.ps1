# Launch MCP Inspector against the development server.
# Requires Node.js (see the Inspector release notes for the current minimum).
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Push-Location $root
try {
    npx "@modelcontextprotocol/inspector" --cli uv run gstarcad-mcp serve @args
} finally {
    Pop-Location
}
