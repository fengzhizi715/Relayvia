"""Authentication boundaries for Relayvia's control and Runner planes.

V1 deliberately uses a single control-plane bearer token instead of a full
identity/RBAC system.  It is a deployment boundary for a trusted team, not a
replacement for SSO.  Runner mutation endpoints use their own enrollment and
per-Runner tokens so a Runner never needs the control-plane credential.
"""

from __future__ import annotations

import hmac

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() == "bearer" and value:
        return value
    return request.headers.get("X-Relayvia-Control-Plane-Token")


def control_plane_authorized(request: Request) -> bool:
    expected = get_settings().control_plane_token
    supplied = _bearer_token(request)
    return bool(expected and supplied and hmac.compare_digest(supplied, expected))


def control_plane_error(request: Request) -> JSONResponse | None:
    settings = get_settings()
    if not settings.control_plane_token:
        return _error(
            503,
            "CONTROL_PLANE_AUTH_NOT_CONFIGURED",
            "Control-plane authentication is not configured",
        )
    if not control_plane_authorized(request):
        return _error(401, "CONTROL_PLANE_AUTH_REQUIRED", "A valid control-plane bearer token is required")
    return None


def runner_enrollment_error(request: Request) -> JSONResponse | None:
    """Authorize first enrollment without exposing a control-plane token.

    Re-registration is authenticated separately using the persisted Runner
    token.  An operator may use the control-plane token for an initial
    enrollment, or provision a runner-specific bootstrap token out of band.
    """
    if control_plane_authorized(request):
        return None
    expected = get_settings().runner_enrollment_token
    supplied = request.headers.get("X-Relayvia-Runner-Enrollment-Token")
    if expected and supplied and hmac.compare_digest(supplied, expected):
        return None
    if not expected:
        return _error(
            503,
            "RUNNER_ENROLLMENT_NOT_CONFIGURED",
            "Runner enrollment requires a configured enrollment token or control-plane bearer token",
        )
    return _error(401, "RUNNER_ENROLLMENT_REQUIRED", "A valid Runner enrollment token is required")


def is_runner_data_plane_request(request: Request) -> bool:
    """Return true only for endpoints protected by Runner-specific tokens."""
    path = request.url.path.rstrip("/")
    if request.method == "POST" and path == "/api/runners/register":
        return True
    parts = path.split("/")
    if request.method != "POST" or parts[:3] != ["", "api", "runners"]:
        return False
    if len(parts) == 5 and parts[4] in {"heartbeat", "claim", "submit-result"}:
        return True
    return len(parts) == 7 and parts[4] == "tasks" and parts[6] == "heartbeat"


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message, "details": {}}})


__all__ = [
    "control_plane_error",
    "control_plane_authorized",
    "is_runner_data_plane_request",
    "runner_enrollment_error",
]
