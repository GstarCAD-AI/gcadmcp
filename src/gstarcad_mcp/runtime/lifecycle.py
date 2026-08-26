"""Server lifecycle helpers."""

from __future__ import annotations

import sys
import uuid


def runtime_id() -> uuid.UUID:
    return uuid.uuid4()


def platform_supported() -> bool:
    return sys.platform == "win32"
