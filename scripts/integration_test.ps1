# Run the real GstarCAD integration suite on a controlled interactive
# Windows machine with GstarCAD installed. Tests run serially against one
# desktop GstarCAD instance.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Push-Location $root
try {
    $env:GSTARCAD_MCP_INTEGRATION = "1"
    uv run pytest tests/integration_windows -q -p no:cacheprovider --maxfail=1 @args
} finally {
    Remove-Item Env:\GSTARCAD_MCP_INTEGRATION -ErrorAction SilentlyContinue
    Pop-Location
}
