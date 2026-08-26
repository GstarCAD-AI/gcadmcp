"""WorkspacePolicy test adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gstarcad_mcp.policy.workspace import WorkspacePolicy


def make_policy(
    workspace_root: Any, *, allow_unc: bool = False, allow_overwrite: bool = False
) -> WorkspacePolicy:
    return WorkspacePolicy(
        Path(workspace_root),
        allow_unc=allow_unc,
        allow_overwrite=allow_overwrite,
    )
