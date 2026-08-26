# Build distribution artifacts for gstarcad-mcp-server.
# PyInstaller is intentionally NOT the first distribution path (see the
# guideline / ADR notes); ship wheel + sdist first.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Push-Location $root
try {
    uv build --wheel --sdist
    uv run pytest tests -q
    Write-Host "Build artifacts are in dist/. Install with:"
    Write-Host "  pipx install gstarcad-mcp-server   # or: uv tool install"
} finally {
    Pop-Location
}
