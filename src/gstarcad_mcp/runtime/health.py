"""Actor runtime states and health (guideline 10.4)."""

from __future__ import annotations

from enum import Enum


class RuntimeState(str, Enum):
    NEW = "new"
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
