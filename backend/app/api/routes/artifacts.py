from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.errors import RelayviaError
from app.domain.artifacts.schemas import ArtifactRead
from app.domain.artifacts.service import get_artifact
from app.infrastructure.artifact_storage import get_artifact_storage
from app.infrastructure.database.session import get_db

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


def _to_read(artifact) -> ArtifactRead:
    return ArtifactRead(
        id=artifact.id,
        workflow_run_id=artifact.workflow_run_id,
        producer_node_run_id=artifact.producer_node_run_id,
        type=artifact.type,
        name=artifact.name,
        uri=artifact.uri,
        size=artifact.size,
        content_type=artifact.content_type,
        metadata=artifact.metadata_json,
        created_at=artifact.created_at,
    )


@router.get("/{artifact_id}", response_model=ArtifactRead)
def get_artifact_detail(artifact_id: str, db: Session = Depends(get_db)) -> ArtifactRead:
    return _to_read(get_artifact(db, artifact_id))


@router.get("/{artifact_id}/content")
def get_artifact_content(artifact_id: str, db: Session = Depends(get_db)):
    artifact = get_artifact(db, artifact_id)
    if artifact.size is None:
        # External URI artifact: there is no local content to stream.
        raise RelayviaError(
            "ARTIFACT_NO_LOCAL_CONTENT",
            "Artifact has no local content (external URI)",
            status_code=404,
        )
    try:
        path = get_artifact_storage().local_path(artifact.id)
    except (FileNotFoundError, RelayviaError) as exc:
        if isinstance(exc, FileNotFoundError):
            raise RelayviaError("ARTIFACT_CONTENT_MISSING", "Artifact content is missing", status_code=404) from exc
        raise
    return FileResponse(
        path,
        media_type=artifact.content_type or "application/octet-stream",
        filename=artifact.name,
    )
