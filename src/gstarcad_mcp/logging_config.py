"""Logging and audit configuration. stdout is reserved for the protocol."""

from __future__ import annotations

import json
import logging
import logging.handlers
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def configure_logging(
    level: str = "INFO",
    *,
    file_path: Path | None = None,
    max_bytes: int = 10_485_760,
    backup_count: int = 5,
) -> None:
    root = logging.getLogger("gstarcad_mcp")
    root.setLevel(level.upper())
    root.propagate = False
    if root.handlers:
        return
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s", "%Y-%m-%dT%H:%M:%S%z"
    )
    stderr = logging.StreamHandler()
    stderr.setFormatter(formatter)
    root.addHandler(stderr)
    if file_path is not None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            file_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


class AuditLogger:
    """Append-only JSONL audit stream for security-relevant events."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def record(self, event: str, **fields: Any) -> None:
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
        }
        row.update(fields)
        line = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        with self._lock, open(self._path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
