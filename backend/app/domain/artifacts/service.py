"""Artifact service: registration and resolution.

Registration belongs to the Runtime (the Worker), not the Connector. A
Connector only describes candidates; this service persists content to the
`ArtifactStorage`, creates the `Artifact` record and returns `artifact://<id>`.
"""

from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import RelayviaError
from app.domain.artifacts.models import Artifact
from app.domain.artifacts.reference import artifact_uri
from app.infrastructure.artifact_storage.base import ArtifactStorage


def _to_read(artifact: Artifact) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "workflow_run_id": artifact.workflow_run_id,
        "producer_node_run_id": artifact.producer_node_run_id,
        "type": artifact.type,
        "name": artifact.name,
        "uri": artifact.uri,
        "size": artifact.size,
        "content_type": artifact.content_type,
        "metadata": artifact.metadata_json,
        "created_at": artifact.created_at,
    }


def register_artifact_bytes(
    db: Session,
    *,
    workflow_run_id: str,
    producer_node_run_id: str,
    name: str,
    artifact_type: str,
    content_type: str | None,
    content: bytes,
    metadata: dict[str, Any] | None,
    storage: ArtifactStorage,
) -> Artifact:
    artifact_id = str(uuid4())
    size = storage.save_bytes(artifact_id, content)
    artifact = Artifact(
        id=artifact_id,
        workflow_run_id=workflow_run_id,
        producer_node_run_id=producer_node_run_id,
        type=artifact_type,
        name=name,
        uri=artifact_uri(artifact_id),
        size=size,
        content_type=content_type,
        metadata_json=dict(metadata or {}),
    )
    db.add(artifact)
    db.flush()
    return artifact


def register_external_artifact(
    db: Session,
    *,
    workflow_run_id: str,
    producer_node_run_id: str,
    name: str,
    artifact_type: str,
    uri: str,
    content_type: str | None,
    metadata: dict[str, Any] | None,
) -> Artifact:
    """An external URI Artifact (e.g. `artifact_url` from an HTTP response).
    No local content is stored; the reference points at the external URI."""
    artifact = Artifact(
        id=str(uuid4()),
        workflow_run_id=workflow_run_id,
        producer_node_run_id=producer_node_run_id,
        type=artifact_type,
        name=name,
        uri=uri,
        size=None,
        content_type=content_type,
        metadata_json=dict(metadata or {}),
    )
    db.add(artifact)
    db.flush()
    return artifact


def register_artifact_candidates(
    db: Session,
    *,
    workflow_run_id: str,
    producer_node_run_id: str,
    candidates: list[dict[str, Any]],
    storage: ArtifactStorage,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Register artifact candidates produced by an ExecutionResult.

    Returns (artifact references, output_key -> artifact://<id> map). A
    candidate is either a local file (`local_path`) or an external URI
    (`uri`). An `output_key` lets the producer expose the reference through
    NodeRun output so downstream nodes can reference it via the Context
    Resolver.
    """
    references: list[dict[str, Any]] = []
    output_map: dict[str, str] = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "artifact")
        artifact_type = str(item.get("type") or "file")
        content_type = item.get("content_type")
        content_type = str(content_type) if content_type else None
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        uri = item.get("uri")

        if item.get("local_path"):
            try:
                content = Path(str(item["local_path"])).read_bytes()
            except OSError:
                continue
            artifact = register_artifact_bytes(
                db,
                workflow_run_id=workflow_run_id,
                producer_node_run_id=producer_node_run_id,
                name=name,
                artifact_type=artifact_type,
                content_type=content_type,
                content=content,
                metadata=metadata,
                storage=storage,
            )
        elif isinstance(uri, str) and uri:
            if uri.startswith("artifact://"):
                # Already a Workflow reference: keep it as-is.
                artifact = None
                reference = {"uri": uri, "type": artifact_type, "name": name}
            else:
                artifact = register_external_artifact(
                    db,
                    workflow_run_id=workflow_run_id,
                    producer_node_run_id=producer_node_run_id,
                    name=name,
                    artifact_type=artifact_type,
                    uri=uri,
                    content_type=content_type,
                    metadata=metadata,
                )
                reference = {"uri": artifact.uri, "type": artifact.type, "name": artifact.name}
        else:
            continue

        if artifact is not None:
            reference = {"uri": artifact.uri, "type": artifact.type, "name": artifact.name}
        references.append(reference)
        output_key = item.get("output_key")
        if isinstance(output_key, str) and output_key:
            output_map[output_key] = reference["uri"]
    return references, output_map


def get_artifact(db: Session, artifact_id: str) -> Artifact:
    artifact = db.get(Artifact, artifact_id)
    if artifact is None:
        raise RelayviaError("ARTIFACT_NOT_FOUND", "Artifact not found", status_code=404)
    return artifact


def get_artifact_or_none(db: Session, artifact_id: str) -> Artifact | None:
    return db.get(Artifact, artifact_id)


def list_artifacts_for_run(db: Session, run_id: str) -> list[dict[str, Any]]:
    artifacts = db.scalars(
        select(Artifact).where(Artifact.workflow_run_id == run_id).order_by(Artifact.created_at)
    ).all()
    return [_to_read(artifact) for artifact in artifacts]


__all__ = [
    "get_artifact",
    "get_artifact_or_none",
    "list_artifacts_for_run",
    "register_artifact_bytes",
    "register_artifact_candidates",
    "register_external_artifact",
]
