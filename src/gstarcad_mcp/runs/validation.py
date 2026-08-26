"""Deterministic structural validation for runs (§16.22)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from gstarcad_mcp.schemas.runs import ValidationCheck

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _check(check_id: str, category: str, ok: bool | None, message: str, uris=None):
    status: Literal["passed", "failed", "not_run"] = (
        "passed" if ok else ("failed" if ok is False else "not_run")
    )
    return ValidationCheck(
        check_id=check_id,
        category=category,
        status=status,
        message=message,
        evidence_uris=uris or [],
    )


def validate_run(
    *,
    run_dir: Path,
    manifest: Any,
    after_inventory: dict | None,
    screenshot_path: Path | None,
    output_dwg_path: Path | None,
    saved_after_last_mutation: bool | None,
    had_partial_commit: bool,
    screenshot_expected: bool = True,
) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []

    checks.append(
        _check(
            "actions_executed",
            "execution",
            (run_dir / "actions.jsonl").exists(),
            (
                "Action journal exists."
                if (run_dir / "actions.jsonl").exists()
                else "No actions were journaled."
            ),
        )
    )

    if after_inventory is not None:
        count = after_inventory.get("count", 0)
        checks.append(
            _check(
                "entity_inventory",
                "structure",
                count >= 0,
                f"Entity inventory captured ({count} entities).",
            )
        )
        layers = {e.get("layer") for e in after_inventory.get("entities", []) if e.get("layer")}
        checks.append(
            _check(
                "layers_present",
                "structure",
                bool(layers),
                f"Layers found: {sorted(layers) or 'none'}.",
            )
        )
    else:
        checks.append(
            _check("entity_inventory", "structure", False, "After-state inventory missing.")
        )

    if screenshot_expected:
        if screenshot_path is not None and screenshot_path.exists():
            data = screenshot_path.read_bytes()
            ok_signature = data.startswith(PNG_SIGNATURE) and len(data) > 0
            checks.append(
                _check(
                    "screenshot_exists",
                    "evidence",
                    True,
                    f"Screenshot present ({len(data)} bytes).",
                )
            )
            checks.append(
                _check(
                    "screenshot_valid_png",
                    "evidence",
                    ok_signature,
                    "PNG signature valid." if ok_signature else "File is not a valid PNG.",
                )
            )
        else:
            checks.append(_check("screenshot_exists", "evidence", False, "Screenshot missing."))
    else:
        checks.append(_check("screenshot_exists", "evidence", None, "Screenshot not expected."))

    if output_dwg_path is not None:
        exists = output_dwg_path.exists() and output_dwg_path.stat().st_size > 0
        checks.append(
            _check(
                "output_dwg_saved",
                "save",
                exists,
                "Output DWG exists and is non-empty." if exists else "Output DWG missing or empty.",
            )
        )
    else:
        checks.append(_check("output_dwg_saved", "save", None, "No output DWG requested."))

    checks.append(
        _check(
            "saved_after_mutation",
            "save",
            saved_after_last_mutation,
            (
                "Document saved after the last mutation."
                if saved_after_last_mutation
                else "Document was not saved after the last mutation."
            ),
        )
    )

    checks.append(
        _check(
            "no_partial_commit",
            "execution",
            not had_partial_commit,
            (
                "No unresolved partial commit."
                if not had_partial_commit
                else "A partial commit occurred."
            ),
        )
    )

    return checks
