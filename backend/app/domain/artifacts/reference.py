"""Artifact URI reference contract.

A Workflow Artifact is referenced by a single stable URI: `artifact://<id>`.
Connectors must not invent their own schemes (file://, model://, ...).
"""

from app.core.errors import RelayviaError

ARTIFACT_URI_PREFIX = "artifact://"


def artifact_uri(artifact_id: str) -> str:
    return f"{ARTIFACT_URI_PREFIX}{artifact_id}"


def is_artifact_uri(value: object) -> bool:
    return isinstance(value, str) and value.startswith(ARTIFACT_URI_PREFIX)


def parse_artifact_uri(value: object) -> str:
    """Return the Artifact id from an `artifact://<id>` reference, or raise."""
    if not is_artifact_uri(value):
        raise RelayviaError("INVALID_ARTIFACT_REFERENCE", "Artifact reference must use artifact://<id>", details={"reference": value})
    artifact_id = value[len(ARTIFACT_URI_PREFIX):]  # type: ignore[index]
    if not artifact_id:
        raise RelayviaError("INVALID_ARTIFACT_REFERENCE", "Artifact reference has no id", details={"reference": value})
    return artifact_id
