"""Workspace sandbox: one canonical resolver for every client path (§15)."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

from gstarcad_mcp.errors import OUTPUT_EXISTS, PATH_DENIED, ExpectedCadError

INPUT_EXTENSIONS = {".dwg", ".dxf"}
OUTPUT_EXTENSIONS = {".dwg", ".dxf", ".png", ".json", ".jsonl", ".md"}

_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

_SUBDIRS = ("inputs", "outputs", "runs", "cache", "state", "logs")


class WorkspacePolicy:
    def __init__(self, root: Path, *, allow_unc: bool = False, allow_overwrite: bool = False):
        self.root = Path(root).resolve()
        self.allow_unc = allow_unc
        self.allow_overwrite = allow_overwrite

    def ensure_layout(self) -> None:
        for name in _SUBDIRS:
            (self.root / name).mkdir(parents=True, exist_ok=True)

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @property
    def outputs_dir(self) -> Path:
        return self.root / "outputs"

    @property
    def inputs_dir(self) -> Path:
        return self.root / "inputs"

    def _validate_relative(self, relative_path: str) -> PurePosixPath:
        if not isinstance(relative_path, str) or not relative_path:
            raise ExpectedCadError(PATH_DENIED, "Empty path is not allowed.")
        if "\x00" in relative_path:
            raise ExpectedCadError(PATH_DENIED, "Path contains a NUL byte.")
        if relative_path != relative_path.strip():
            raise ExpectedCadError(PATH_DENIED, "Path has leading or trailing whitespace.")
        text = relative_path.replace("\\", "/")
        if text.startswith("//") or text.startswith("\\\\"):
            if not self.allow_unc:
                raise ExpectedCadError(PATH_DENIED, "UNC/network paths are not allowed.")
        if ":" in text:
            raise ExpectedCadError(PATH_DENIED, "Absolute or stream paths are not allowed.")
        if text.startswith("/"):
            raise ExpectedCadError(PATH_DENIED, "Absolute paths are not allowed.")
        pure = PurePosixPath(text)
        parts = pure.parts
        if not parts:
            raise ExpectedCadError(PATH_DENIED, "Empty path is not allowed.")
        if any(part in {"..", "."} for part in parts):
            raise ExpectedCadError(PATH_DENIED, "Path traversal is not allowed.")
        for part in parts:
            stem = part.split(".")[0].upper()
            if stem in _RESERVED_NAMES:
                raise ExpectedCadError(PATH_DENIED, f"Reserved Windows name: {part}")
            if part.endswith(".") or part.endswith(" "):
                raise ExpectedCadError(PATH_DENIED, f"Invalid trailing character in: {part}")
            if len(part) > 200:
                raise ExpectedCadError(PATH_DENIED, "Path component too long.")
        return pure

    def _resolve(self, relative_path: str, allowed_extensions: set[str]) -> Path:
        pure = self._validate_relative(relative_path)
        ext = PureWindowsPath(pure.name).suffix.lower()
        if ext not in allowed_extensions:
            raise ExpectedCadError(
                PATH_DENIED,
                f"Extension '{ext or '(none)'}' is not allowed; "
                f"expected one of {sorted(allowed_extensions)}.",
            )
        candidate = (self.root / Path(*pure.parts)).resolve()
        if self.root not in candidate.parents and candidate != self.root:
            raise ExpectedCadError(PATH_DENIED, "Path escapes the workspace (symlink/junction).")
        return candidate

    def resolve_input(
        self, relative_path: str, *, allowed_extensions: set[str] | None = None
    ) -> Path:
        path = self._resolve(relative_path, allowed_extensions or INPUT_EXTENSIONS)
        if not path.is_file():
            raise ExpectedCadError(PATH_DENIED, f"Input not found: {relative_path}")
        return path

    def resolve_output(
        self,
        relative_path: str,
        *,
        overwrite: bool = False,
        allowed_extensions: set[str] | None = None,
    ) -> Path:
        path = self._resolve(relative_path, allowed_extensions or OUTPUT_EXTENSIONS)
        outputs_root = self.outputs_dir.resolve()
        if outputs_root not in path.parents:
            raise ExpectedCadError(
                PATH_DENIED, "Outputs must be written under the outputs/ directory."
            )
        if path.exists():
            if not (overwrite or self.allow_overwrite):
                raise ExpectedCadError(
                    OUTPUT_EXISTS,
                    f"Output already exists: {relative_path}. Pass overwrite=true to replace it.",
                )
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def resolve_artifact(self, relative_path: str) -> Path:
        """Resolve a known-good workspace-relative artifact for reading."""
        pure = self._validate_relative(relative_path)
        candidate = (self.root / Path(*pure.parts)).resolve()
        if self.root not in candidate.parents:
            raise ExpectedCadError(PATH_DENIED, "Path escapes the workspace.")
        return candidate

    def relative(self, path: Path) -> str:
        return Path(path).resolve().relative_to(self.root).as_posix()
