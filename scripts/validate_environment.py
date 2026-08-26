"""Validate the local environment for gstarcad-mcp-server.

Thin wrapper over ``gstarcad_mcp.cli`` so the script can be run from a
checkout without installing the console entry point:

    python scripts/validate_environment.py [--json]
"""

from __future__ import annotations

import sys


def main() -> int:
    argv = ["validate-env", *sys.argv[1:]]
    try:
        from gstarcad_mcp.cli import main as cli_main
    except ImportError:
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from gstarcad_mcp.cli import main as cli_main
    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
