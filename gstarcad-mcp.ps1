[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Command = "help",

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$CommandArguments = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Show-Usage {
    @"
Usage:
  .\gstarcad-mcp.ps1 setup [--resync]
  .\gstarcad-mcp.ps1 run [SERVER_ARGS...]
  .\gstarcad-mcp.ps1 serve [SERVER_ARGS...]
  .\gstarcad-mcp.ps1 status
  .\gstarcad-mcp.ps1 validate-env [--json]
  .\gstarcad-mcp.ps1 print-config
  .\gstarcad-mcp.ps1 list-tools
  .\gstarcad-mcp.ps1 test [--live] [PYTEST_ARGS...]
  .\gstarcad-mcp.ps1 smoke [--full|--workflow] [--prog-id PROGID]
  .\gstarcad-mcp.ps1 inspector
  .\gstarcad-mcp.ps1 version
  .\gstarcad-mcp.ps1 help

Commands:
  setup         Create/refresh the uv environment (uv sync --all-extras).
  run           One-shot: set up the environment and start the stdio MCP
                server (alias of serve).
  serve         Run the stdio MCP server (what MCP hosts launch). Extra
                arguments are passed through to gstarcad-mcp.
  status        Quick diagnostic (no CAD session required).
  validate-env  Environment checks; add --json for scripts.
  print-config  Effective non-secret configuration.
  list-tools    Tool catalog without starting CAD.
  test          Fake-COM unit + in-memory MCP contract tests; --live adds
                the real-GstarCAD pytest suite (needs Windows + GstarCAD).
  smoke         Live end-to-end smokes over real stdio against GstarCAD:
                --workflow (default) runs the prompt-driven drawing
                workflow; --full runs all 55 checks.
  inspector     Launch MCP Inspector against the server.
  version       Print the server version.

Environment:
  GSTARCAD_MCP_WORKSPACE_ROOT      Workspace sandbox root (recommended for
                                   serve/smoke; otherwise a default under
                                   Documents is used).
  GSTARCAD_MCP_PROG_ID             Pin a GstarCAD version, e.g.
                                   GStarCAD.Application.26 or .27
                                   (default: auto-discover, newest first).
  GSTARCAD_MCP_PERMISSION_PROFILE  readonly | assistive | authoring |
                                   automation (default: authoring).
  GSTARCAD_MCP_CONFIG              Optional TOML configuration file.

Examples:
  .\gstarcad-mcp.ps1 setup
  .\gstarcad-mcp.ps1 validate-env
  .\gstarcad-mcp.ps1 test
  .\gstarcad-mcp.ps1 smoke --full --prog-id GStarCAD.Application.26
"@
}

$script:ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Invoke-External {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = $script:ScriptDir
    )

    $command = Get-Command -Name $Name -CommandType Application -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "$Name is not installed or not on PATH"
    }
    $commandPath = $command.Path
    if ([string]::IsNullOrWhiteSpace($commandPath)) {
        $commandPath = $command.Source
    }
    $exitCode = 0
    Push-Location -LiteralPath $WorkingDirectory
    try {
        & $commandPath @Arguments
        if ($null -ne $LASTEXITCODE) {
            $exitCode = $LASTEXITCODE
        }
    }
    finally {
        Pop-Location
    }
    if ($exitCode -ne 0) {
        throw "$Name exited with code $exitCode"
    }
}

function Require-Uv {
    try {
        Invoke-External "uv" @("--version")
    }
    catch {
        throw "uv is required. Install it from https://docs.astral.sh/uv/ and re-run."
    }
}

function Ensure-Environment {
    param([switch]$Resync)

    Require-Uv
    $lockfile = Join-Path $script:ScriptDir "uv.lock"
    if (-not (Test-Path -LiteralPath $lockfile -PathType Leaf)) {
        throw "Missing uv.lock next to this script; are you in the gstarcad-mcp-server checkout?"
    }
    $syncArgs = @("sync", "--all-extras")
    if ($Resync) {
        $syncArgs += "--reinstall"
    }
    Write-Host "== uv sync --all-extras"
    Invoke-External "uv" $syncArgs
}

function Invoke-ServerCommand {
    param([string]$Name, [string[]]$Arguments = @())

    Ensure-Environment
    Invoke-External "uv" (@("run", "gstarcad-mcp", $Name) + @($Arguments))
}

function Invoke-Setup {
    $resync = $false
    foreach ($argument in @($CommandArguments)) {
        switch -Regex ([string]$argument) {
            "^--?(re-?sync)$" { $resync = $true }
            "^-h$|^--help$" { Show-Usage; return }
            default { throw "Unknown setup argument: $argument" }
        }
    }
    Ensure-Environment -Resync:$resync
    Write-Host "ok: environment ready. Try: .\gstarcad-mcp.ps1 validate-env"
}

function Invoke-Test {
    $live = $false
    $pytestArgs = @()
    foreach ($argument in @($CommandArguments)) {
        switch -Regex ([string]$argument) {
            "^--?live$" { $live = $true }
            "^-h$|^--help$" { Show-Usage; return }
            default { $pytestArgs += $argument }
        }
    }
    Ensure-Environment
    if ($live) {
        Write-Host "== unit tests + live GstarCAD pytest suite"
        $env:GSTARCAD_MCP_INTEGRATION = "1"
        try {
            Invoke-External "uv" (@("run", "pytest", "tests", "-q") + @($pytestArgs))
        }
        finally {
            Remove-Item Env:\GSTARCAD_MCP_INTEGRATION -ErrorAction SilentlyContinue
        }
    }
    else {
        Write-Host "== unit tests (fake COM)"
        Invoke-External "uv" (@("run", "pytest", "tests", "-q") + @($pytestArgs))
    }
}

function Invoke-Smoke {
    $variant = "workflow"
    $progId = ""
    $tokens = @($CommandArguments)
    for ($index = 0; $index -lt $tokens.Count; $index++) {
        $token = [string]$tokens[$index]
        switch -Regex ($token) {
            "^--?full$" { $variant = "full" }
            "^--?workflow$" { $variant = "workflow" }
            "^--?prog-id$" {
                if ($index + 1 -ge $tokens.Count) {
                    throw "--prog-id requires a ProgID"
                }
                $progId = [string]$tokens[++$index]
            }
            "^-h$|^--help$" { Show-Usage; return }
            default { throw "Unknown smoke argument: $token" }
        }
    }
    Ensure-Environment
    if ($progId) {
        $env:GSTARCAD_MCP_PROG_ID = $progId
    }
    $script = if ($variant -eq "full") { "scripts\smoke_full.py" } else { "scripts\smoke_mcp.py" }
    Write-Host "== live smoke ($variant) against GstarCAD"
    try {
        Invoke-External "uv" @("run", "python", (Join-Path $script:ScriptDir $script))
    }
    finally {
        if ($progId) {
            Remove-Item Env:\GSTARCAD_MCP_PROG_ID -ErrorAction SilentlyContinue
        }
    }
}

function Invoke-Inspector {
    Ensure-Environment
    Write-Host "== MCP Inspector (requires Node.js)"
    Invoke-External "npx" @("@modelcontextprotocol/inspector", "--cli", "uv", "run", "gstarcad-mcp", "serve")
}

try {
    switch ($Command.ToLowerInvariant()) {
        "setup" { Invoke-Setup }
        "run" { Invoke-ServerCommand "serve" $CommandArguments }
        "serve" { Invoke-ServerCommand "serve" $CommandArguments }
        "status" { Invoke-ServerCommand "status" $CommandArguments }
        "validate-env" { Invoke-ServerCommand "validate-env" $CommandArguments }
        "print-config" { Invoke-ServerCommand "print-config" $CommandArguments }
        "list-tools" { Invoke-ServerCommand "list-tools" $CommandArguments }
        "test" { Invoke-Test }
        "smoke" { Invoke-Smoke }
        "inspector" { Invoke-Inspector }
        "version" { Invoke-ServerCommand "version" }
        "help" { Show-Usage }
        "-h" { Show-Usage }
        "--help" { Show-Usage }
        default { throw "Unknown command: $Command" }
    }
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
