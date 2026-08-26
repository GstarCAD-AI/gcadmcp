"""Permission profiles enforced server-side (guideline 14)."""

from __future__ import annotations

from enum import Enum

from gstarcad_mcp.errors import PERMISSION_DENIED, ExpectedCadError

READONLY = "readonly"
ASSISTIVE = "assistive"
AUTHORING = "authoring"
AUTOMATION = "automation"


class PermissionProfile(str, Enum):
    READONLY = READONLY
    ASSISTIVE = ASSISTIVE
    AUTHORING = AUTHORING
    AUTOMATION = AUTOMATION


# capability -> set of profiles allowed
_MATRIX: dict[str, set[str]] = {
    "cad.status.read": {READONLY, ASSISTIVE, AUTHORING, AUTOMATION},
    "cad.document.read": {READONLY, ASSISTIVE, AUTHORING, AUTOMATION},
    "cad.entity.read": {READONLY, ASSISTIVE, AUTHORING, AUTOMATION},
    "cad.view.capture": {READONLY, ASSISTIVE, AUTHORING, AUTOMATION},
    "cad.run.manage": {READONLY, ASSISTIVE, AUTHORING, AUTOMATION},
    "cad.document.create": {ASSISTIVE, AUTHORING, AUTOMATION},
    "cad.document.open": {ASSISTIVE, AUTHORING, AUTOMATION},
    "cad.layer.create": {ASSISTIVE, AUTHORING, AUTOMATION},
    "cad.entity.create": {ASSISTIVE, AUTHORING, AUTOMATION},
    "cad.view.modify": {ASSISTIVE, AUTHORING, AUTOMATION},
    "cad.document.save": {ASSISTIVE, AUTHORING, AUTOMATION},
    "cad.document.close": {AUTHORING, AUTOMATION},
    "cad.entity.update": {ASSISTIVE, AUTHORING, AUTOMATION},
    "cad.entity.delete": {ASSISTIVE, AUTHORING, AUTOMATION},
    "cad.document.discard": {AUTHORING, AUTOMATION},
    "cad.application.quit": {AUTHORING, AUTOMATION},
}


def check_permission(profile: str, permission: str) -> None:
    allowed = _MATRIX.get(permission)
    if allowed is None:
        raise ExpectedCadError(PERMISSION_DENIED, f"Unknown permission: {permission}")
    if profile not in allowed:
        raise ExpectedCadError(
            PERMISSION_DENIED,
            f"Profile '{profile}' is not allowed to perform '{permission}'.",
        )


def check_external_document_action(profile: str, action: str) -> None:
    """Restrictions for external (user-owned) documents (guideline 12.6)."""
    denied = {
        "close": {READONLY, ASSISTIVE, AUTOMATION},
        "save_in_place": {READONLY, AUTOMATION},
        "discard": {READONLY, ASSISTIVE, AUTOMATION},
        "edit": {READONLY, AUTOMATION},
    }
    profiles = denied.get(action)
    if profiles and profile in profiles:
        raise ExpectedCadError(
            PERMISSION_DENIED,
            f"Profile '{profile}' may not {action} an external document.",
        )
