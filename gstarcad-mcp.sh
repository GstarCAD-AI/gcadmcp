#!/usr/bin/env bash
# gstarcad-mcp.sh - user entry point for the gstarcad-mcp-server project.
#
# Live CAD operations (serve against GstarCAD, smoke, test --live) require
# Windows with GstarCAD installed; on other platforms the server still runs
# in degraded mode and schema/contract tests pass.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<'USAGE'
Usage:
  ./gstarcad-mcp.sh setup [--resync]
  ./gstarcad-mcp.sh run [SERVER_ARGS...]
  ./gstarcad-mcp.sh serve [SERVER_ARGS...]
  ./gstarcad-mcp.sh status
  ./gstarcad-mcp.sh validate-env [--json]
  ./gstarcad-mcp.sh print-config
  ./gstarcad-mcp.sh list-tools
  ./gstarcad-mcp.sh test [--live] [PYTEST_ARGS...]
  ./gstarcad-mcp.sh smoke [--full|--workflow] [--prog-id PROGID]
  ./gstarcad-mcp.sh inspector
  ./gstarcad-mcp.sh version
  ./gstarcad-mcp.sh help

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
  ./gstarcad-mcp.sh setup
  ./gstarcad-mcp.sh validate-env
  ./gstarcad-mcp.sh test
  ./gstarcad-mcp.sh smoke --full --prog-id GStarCAD.Application.26
USAGE
}

require_uv() {
    if ! command -v uv >/dev/null 2>&1; then
        echo "error: uv is required. Install it from https://docs.astral.sh/uv/ and re-run." >&2
        exit 2
    fi
}

ensure_environment() {
    local resync="${1:-0}"
    require_uv
    if [[ ! -f "${SCRIPT_DIR}/uv.lock" ]]; then
        echo "error: missing uv.lock next to this script; are you in the gstarcad-mcp-server checkout?" >&2
        exit 2
    fi
    local sync_args=(sync --all-extras)
    if [[ "${resync}" -eq 1 ]]; then
        sync_args+=(--reinstall)
    fi
    echo "== uv sync --all-extras"
    (cd "${SCRIPT_DIR}" && uv "${sync_args[@]}")
}

warn_if_not_windows() {
    case "$(uname -s 2>/dev/null || echo unknown)" in
        CYGWIN*|MINGW*|MSYS*|Windows_NT) ;;
        *)
            echo "warning: live GstarCAD automation needs Windows; the server runs" >&2
            echo "         in degraded mode here and schema/contract tests still pass." >&2
            ;;
    esac
}

run_cli() {
    local name="$1"
    shift
    ensure_environment 0
    (cd "${SCRIPT_DIR}" && uv run gstarcad-mcp "${name}" "$@")
}

cmd_setup() {
    local resync=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --resync|--re-sync) resync=1; shift ;;
            -h|--help) usage; exit 0 ;;
            *) echo "error: unknown setup argument: $1" >&2; exit 2 ;;
        esac
    done
    ensure_environment "${resync}"
    echo "ok: environment ready. Try: ./gstarcad-mcp.sh validate-env"
}

cmd_serve() {
    warn_if_not_windows
    run_cli serve "$@"
}

cmd_test() {
    local live=0
    local pytest_args=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --live) live=1; shift ;;
            -h|--help) usage; exit 0 ;;
            *) pytest_args+=("$1"); shift ;;
        esac
    done
    ensure_environment 0
    if [[ "${live}" -eq 1 ]]; then
        warn_if_not_windows
        echo "== unit tests + live GstarCAD pytest suite"
        (cd "${SCRIPT_DIR}" && GSTARCAD_MCP_INTEGRATION=1 uv run pytest tests -q "${pytest_args[@]}")
    else
        echo "== unit tests (fake COM)"
        (cd "${SCRIPT_DIR}" && uv run pytest tests -q "${pytest_args[@]}")
    fi
}

cmd_smoke() {
    local variant="workflow"
    local prog_id=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --full) variant="full"; shift ;;
            --workflow) variant="workflow"; shift ;;
            --prog-id)
                if [[ $# -lt 2 || "$2" == -* ]]; then
                    echo "error: --prog-id requires a ProgID" >&2
                    exit 2
                fi
                prog_id="$2"
                shift 2
                ;;
            -h|--help) usage; exit 0 ;;
            *) echo "error: unknown smoke argument: $1" >&2; exit 2 ;;
        esac
    done
    warn_if_not_windows
    ensure_environment 0
    local script="scripts/smoke_mcp.py"
    if [[ "${variant}" == "full" ]]; then
        script="scripts/smoke_full.py"
    fi
    echo "== live smoke (${variant}) against GstarCAD"
    if [[ -n "${prog_id}" ]]; then
        (cd "${SCRIPT_DIR}" && GSTARCAD_MCP_PROG_ID="${prog_id}" uv run python "${script}")
    else
        (cd "${SCRIPT_DIR}" && uv run python "${script}")
    fi
}

cmd_inspector() {
    ensure_environment 0
    echo "== MCP Inspector (requires Node.js)"
    (cd "${SCRIPT_DIR}" && npx "@modelcontextprotocol/inspector" --cli uv run gstarcad-mcp serve)
}

cmd="${1:-help}"
shift || true

case "${cmd}" in
    setup) cmd_setup "$@" ;;
    run) cmd_serve "$@" ;;
    serve) cmd_serve "$@" ;;
    status) run_cli status "$@" ;;
    validate-env) run_cli validate-env "$@" ;;
    print-config) run_cli print-config "$@" ;;
    list-tools) run_cli list-tools "$@" ;;
    test) cmd_test "$@" ;;
    smoke) cmd_smoke "$@" ;;
    inspector) cmd_inspector "$@" ;;
    version) run_cli version ;;
    help|-h|--help) usage ;;
    *)
        echo "unknown command: ${cmd}" >&2
        usage
        exit 2
        ;;
esac
