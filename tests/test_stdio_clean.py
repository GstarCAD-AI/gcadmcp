"""stdio cleanliness test (guideline §13.4, §37).

For a stdio server, stdout is the protocol transport.  Importing the server
module and constructing the MCP server must write nothing to stdout.
"""

from __future__ import annotations

import os
import subprocess
import sys

SNIPPET = (
    "import gstarcad_mcp.server as server_module\n"
    "server = server_module.create_server()\n"
    "assert server is not None\n"
)


def test_import_and_construct_writes_nothing_to_stdout(tmp_path):
    env = dict(os.environ)
    # Point the default workspace at a scratch directory so construction has
    # no side effects on the real user workspace.
    env["GSTARCAD_MCP_WORKSPACE_ROOT"] = str(tmp_path / "workspace")
    env["PYTHONIOENCODING"] = "utf-8"

    completed = subprocess.run(
        [sys.executable, "-c", SNIPPET],
        capture_output=True,
        env=env,
        timeout=90,
        check=False,
    )
    assert completed.returncode == 0, (
        "server construction failed:\n"
        f"stdout={completed.stdout!r}\nstderr={completed.stderr.decode('utf-8', 'replace')}"
    )
    assert completed.stdout == b"", (
        "stdout must stay clean for the stdio transport; got: "
        f"{completed.stdout.decode('utf-8', 'replace')!r}"
    )


def test_import_writes_nothing_to_stdout():
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, "-c", "import gstarcad_mcp.server"],
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    assert completed.stdout == b"", (
        "importing gstarcad_mcp.server must not print: "
        f"{completed.stdout.decode('utf-8', 'replace')!r}"
    )
