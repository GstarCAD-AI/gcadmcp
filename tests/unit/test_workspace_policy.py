"""WorkspacePolicy sandbox tests (§15, §31.1): hostile paths, symlink escape, outputs."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from support.harness import error_code_value
from support.workspace import make_policy

from gstarcad_mcp.errors import OUTPUT_EXISTS, PATH_DENIED, ExpectedCadError


def _expect_denied(policy, resolver: str, relative_path: str, *, code: str = PATH_DENIED) -> Path:
    fn = getattr(policy, resolver)
    with pytest.raises(ExpectedCadError) as excinfo:
        fn(relative_path)
    exc = excinfo.value
    assert exc.code == error_code_value(code)
    # Sanitization: client-visible text must never contain a stack trace.
    assert "Traceback" not in exc.client_message()
    return exc


# --- hostile inputs -----------------------------------------------------------


@pytest.mark.parametrize(
    "relative_path",
    [
        "..",
        "../secrets.dwg",
        "inputs/../../etc/passwd.dwg",
        "/etc/passwd.dwg",
        "/inputs/sample.dwg",
        "C:/Windows/system32/config.dwg",
        "D:\\projects\\outside.dwg",
        "inputs/stream:evil.dwg",  # NTFS alternate data stream
        "inputs/CON.dwg",
        "inputs/NUL.dwg",
        "inputs/COM1.dwg",
        "inputs/LPT2.dwg",
        "inputs/./sample.dwg",
        "inputs/foo./x.dwg",  # component with trailing dot
        "inputs/foo /x.dwg",  # component with trailing space
        "   ",  # whitespace only
        "",
        ("inputs/" + "a" * 201 + ".dwg"),  # component too long
    ],
)
def test_resolve_input_denies_hostile_paths(workspace_root: Path, relative_path: str) -> None:
    policy = make_policy(workspace_root)
    _expect_denied(policy, "resolve_input", relative_path)


def test_resolve_input_denies_unc_by_default(workspace_root: Path) -> None:
    policy = make_policy(workspace_root)
    _expect_denied(policy, "resolve_input", "//server/share/drawing.dwg")
    _expect_denied(policy, "resolve_input", "\\\\server\\share\\drawing.dwg")


def test_resolve_output_denies_hostile_paths(workspace_root: Path) -> None:
    policy = make_policy(workspace_root)
    _expect_denied(policy, "resolve_output", "../outside.dwg")
    _expect_denied(policy, "resolve_output", "C:/temp/out.dwg")
    _expect_denied(policy, "resolve_output", "//server/share/out.dwg")


@pytest.mark.parametrize(
    "relative_path",
    [
        "inputs/file.pdf",
        "inputs/file.exe",
        "inputs/noextension",
    ],
)
def test_resolve_input_denies_bad_extensions(workspace_root: Path, relative_path: str) -> None:
    policy = make_policy(workspace_root)
    _expect_denied(policy, "resolve_input", relative_path)


@pytest.mark.parametrize(
    "relative_path",
    [
        "outputs/file.exe",
        "outputs/file.bat",
        "outputs/noextension",
    ],
)
def test_resolve_output_denies_bad_extensions(workspace_root: Path, relative_path: str) -> None:
    policy = make_policy(workspace_root)
    _expect_denied(policy, "resolve_output", relative_path)


# --- symlink escape -----------------------------------------------------------


def test_symlink_cannot_escape_workspace(workspace_root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.dwg"
    secret.write_bytes(b"secret")

    policy = make_policy(workspace_root)
    policy.ensure_layout()
    link = workspace_root / "inputs" / "link.dwg"
    try:
        os.symlink(secret, link)
    except OSError as exc:
        pytest.skip(f"cannot create symlinks on this system: {exc}")

    _expect_denied(policy, "resolve_input", "inputs/link.dwg")


def test_symlink_inside_workspace_is_allowed(workspace_root: Path) -> None:
    policy = make_policy(workspace_root)
    policy.ensure_layout()
    real = workspace_root / "inputs" / "real.dwg"
    real.write_bytes(b"dwg")
    link = workspace_root / "inputs" / "alias.dwg"
    try:
        os.symlink(real, link)
    except OSError as exc:
        pytest.skip(f"cannot create symlinks on this system: {exc}")

    resolved = policy.resolve_input("inputs/alias.dwg")
    assert resolved == real.resolve()


# --- happy paths ---------------------------------------------------------------


def test_resolve_input_returns_file_inside_workspace(workspace_root: Path) -> None:
    policy = make_policy(workspace_root)
    policy.ensure_layout()
    sample = workspace_root / "inputs" / "sample.dwg"
    sample.write_bytes(b"dwg-bytes")

    resolved = policy.resolve_input("inputs/sample.dwg")
    assert resolved == sample.resolve()
    assert workspace_root.resolve() in resolved.parents


def test_resolve_input_missing_file_denied(workspace_root: Path) -> None:
    policy = make_policy(workspace_root)
    _expect_denied(policy, "resolve_input", "inputs/ghost.dwg")


def test_resolve_output_creates_parents_and_detects_existing(workspace_root: Path) -> None:
    policy = make_policy(workspace_root)
    policy.ensure_layout()

    target = policy.resolve_output("outputs/nested/final.dwg")
    assert target.parent.is_dir()
    assert target.parent == (workspace_root / "outputs" / "nested").resolve()

    target.write_bytes(b"existing")
    with pytest.raises(ExpectedCadError) as excinfo:
        policy.resolve_output("outputs/nested/final.dwg")
    assert excinfo.value.code == error_code_value(OUTPUT_EXISTS)

    # overwrite flag allows replacement
    again = policy.resolve_output("outputs/nested/final.dwg", overwrite=True)
    assert again == target


def test_allow_overwrite_policy_flag(workspace_root: Path) -> None:
    policy = make_policy(workspace_root, allow_overwrite=True)
    policy.ensure_layout()
    target = workspace_root / "outputs" / "again.dwg"
    target.write_bytes(b"x")
    assert policy.resolve_output("outputs/again.dwg") == target.resolve()


def test_template_extensions_allowed_for_inputs(workspace_root: Path) -> None:
    policy = make_policy(workspace_root)
    policy.ensure_layout()
    template = workspace_root / "inputs" / "base.dwt"
    template.write_bytes(b"dwt")
    resolved = policy.resolve_input("inputs/base.dwt", allowed_extensions={".dwt", ".dwg", ".dxf"})
    assert resolved == template.resolve()
