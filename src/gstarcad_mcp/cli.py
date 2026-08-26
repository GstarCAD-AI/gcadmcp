"""Command-line entry points (§29)."""

from __future__ import annotations

import argparse
import json
import sys

from gstarcad_mcp import SERVER_NAME, SERVER_VERSION


def _cmd_serve(args: argparse.Namespace) -> int:
    from gstarcad_mcp.config import load_config
    from gstarcad_mcp.server import create_server

    config = load_config(args.config)
    server = create_server(config)
    server.run()
    return 0


def _probe_gstarcad() -> dict:
    try:
        from pygcadwin._com import registered_gstarcad_prog_ids

        return {"available": True, "prog_ids": registered_gstarcad_prog_ids()}
    except Exception as exc:
        return {"available": False, "prog_ids": [], "error": str(exc)}


def _cmd_status(args: argparse.Namespace) -> int:
    from gstarcad_mcp.config import load_config
    from gstarcad_mcp.runtime.lifecycle import platform_supported

    config = load_config(args.config)
    platform_ok = platform_supported()
    gstarcad = _probe_gstarcad()
    report = {
        "server": {"name": SERVER_NAME, "version": SERVER_VERSION},
        "platform_supported": platform_ok,
        "python": sys.version.split()[0],
        "permission_profile": config.server.permission_profile,
        "workspace_root": str(config.workspace_root()),
        "gstarcad": gstarcad,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if platform_ok and gstarcad["available"] else 1


def _cmd_validate_env(args: argparse.Namespace) -> int:
    from gstarcad_mcp.config import load_config
    from gstarcad_mcp.policy.workspace import WorkspacePolicy
    from gstarcad_mcp.runtime.lifecycle import platform_supported

    checks: list[dict] = []

    def check(check_id: str, passed: bool, message: str) -> None:
        checks.append(
            {"check_id": check_id, "status": "passed" if passed else "failed", "message": message}
        )

    check(
        "platform_windows",
        platform_supported(),
        (
            "Windows platform"
            if platform_supported()
            else "non-Windows platform: CAD tools unavailable"
        ),
    )

    config = load_config(args.config)
    root = config.workspace_root()
    try:
        WorkspacePolicy(root).ensure_layout()
        write_probe = root / "state" / ".write-probe"
        write_probe.write_text("ok", encoding="utf-8")
        write_probe.unlink()
        check("workspace_writable", True, f"workspace writable: {root}")
    except Exception as exc:
        check("workspace_writable", False, f"workspace not writable: {exc}")

    probe = _probe_gstarcad()
    check(
        "gstarcad_registered",
        probe["available"] and bool(probe["prog_ids"]),
        (
            f"registered ProgIDs: {probe['prog_ids']}"
            if probe["available"]
            else probe.get("error", "probe failed")
        ),
    )

    try:
        import mcp  # noqa: F401

        check("mcp_sdk", True, "mcp SDK importable")
    except Exception as exc:
        check("mcp_sdk", False, f"mcp SDK import failed: {exc}")

    try:
        import pygcadwin  # noqa: F401

        check("pygcadwin", True, "pygcadwin importable")
    except Exception as exc:
        check("pygcadwin", False, f"pygcadwin import failed: {exc}")

    ok = all(c["status"] == "passed" for c in checks)
    payload = {"ok": ok, "checks": checks}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for c in checks:
            print(f"[{c['status'].upper()}] {c['check_id']}: {c['message']}")
    return 0 if ok else 1


def _cmd_print_config(args: argparse.Namespace) -> int:
    from gstarcad_mcp.config import load_config

    config = load_config(args.config)
    print(config.model_dump_json(indent=2))
    return 0


def _cmd_list_tools(_: argparse.Namespace) -> int:
    from gstarcad_mcp.tools import TOOL_CATALOG

    print(json.dumps(TOOL_CATALOG, indent=2, ensure_ascii=False))
    return 0


def _cmd_version(_: argparse.Namespace) -> int:
    print(f"{SERVER_NAME} {SERVER_VERSION}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gstarcad-mcp", description="GstarCAD MCP server")
    parser.add_argument("--config", help="Path to a TOML configuration file")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="Run the MCP server on stdio").set_defaults(func=_cmd_serve)
    sub.add_parser("status", help="Print a runtime status report").set_defaults(func=_cmd_status)
    validate = sub.add_parser("validate-env", help="Validate the host environment")
    validate.add_argument("--json", action="store_true", help="Emit JSON output")
    validate.set_defaults(func=_cmd_validate_env)
    sub.add_parser("print-config", help="Print the resolved configuration").set_defaults(
        func=_cmd_print_config
    )
    sub.add_parser("list-tools", help="List the tool catalog").set_defaults(func=_cmd_list_tools)
    sub.add_parser("version", help="Print the server version").set_defaults(func=_cmd_version)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
