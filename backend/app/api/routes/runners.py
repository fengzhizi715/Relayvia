from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import JSONResponse
from tempfile import SpooledTemporaryFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import RelayviaError
from app.domain.runners.schemas import (
    RunnerClaimRead,
    RunnerHeartbeat,
    RunnerRegistrationRead,
    RunnerRead,
    RunnerRegister,
    RunnerStatusUpdate,
    RunnerTaskHeartbeatRead,
    RunnerTokenRead,
    RunnerSubmitRequest,
    RunnerWorkspaceCleanupClaim,
    RunnerWorkspaceCleanupResult,
)
from app.domain.runners.service import (
    get_runner,
    authenticate_runner,
    heartbeat_runner,
    register_runner,
    revoke_runner,
    rotate_runner_token,
    runner_claim,
    runner_submit,
    runner_task_heartbeat,
    set_runner_enabled,
    to_read,
)
from app.domain.runners.models import Runner, RunnerStatus, runner_online
from app.infrastructure.artifact_storage import get_artifact_storage
from app.infrastructure.database.session import get_db
from app.domain.workspaces.service import claim_workspace_cleanup, complete_workspace_cleanup
from app.domain.artifacts.schemas import RunnerArtifactUploadCreate, RunnerArtifactUploadRead
from app.domain.artifacts.service import (
    create_runner_artifact_upload,
    fail_runner_artifact_upload,
    finalize_runner_artifact_upload,
    validate_runner_artifact_upload,
)
from app.api.security import runner_enrollment_error

router = APIRouter(prefix="/runners", tags=["runners"])


def _settings():
    return get_settings()


@router.get("", response_model=list[RunnerRead])
def get_runners(
    response: Response,
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[RunnerRead]:
    response.headers["X-Total-Count"] = str(db.scalar(select(func.count()).select_from(Runner)) or 0)
    query = select(Runner).order_by(Runner.name).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    runners = db.scalars(query).all()
    offline_after = _settings().runner_offline_seconds
    return [RunnerRead(**to_read(runner, offline_after_seconds=offline_after)) for runner in runners]


@router.get("/{runner_id}", response_model=RunnerRead)
def get_runner_detail(runner_id: str, db: Session = Depends(get_db)) -> RunnerRead:
    runner = get_runner(db, runner_id, offline_after_seconds=_settings().runner_offline_seconds)
    return RunnerRead(**to_read(runner, offline_after_seconds=_settings().runner_offline_seconds))


@router.patch("/{runner_id}", response_model=RunnerRead)
def patch_runner(runner_id: str, payload: RunnerStatusUpdate, db: Session = Depends(get_db)) -> RunnerRead:
    runner = set_runner_enabled(db, runner_id, enabled=payload.enabled)
    return RunnerRead(**to_read(runner, offline_after_seconds=_settings().runner_offline_seconds))


@router.post("/{runner_id}/rotate-token", response_model=RunnerTokenRead)
def post_rotate_runner_token(runner_id: str, db: Session = Depends(get_db)) -> RunnerTokenRead:
    runner, token = rotate_runner_token(db, runner_id)
    return RunnerTokenRead(runner_id=runner.id, enrollment_token=token)


@router.post("/{runner_id}/revoke", response_model=RunnerRead)
def post_revoke_runner(runner_id: str, db: Session = Depends(get_db)) -> RunnerRead:
    runner = revoke_runner(db, runner_id)
    return RunnerRead(**to_read(runner, offline_after_seconds=_settings().runner_offline_seconds))


def _runner_token(x_relayvia_runner_token: str | None = Header(default=None)) -> str | None:
    return x_relayvia_runner_token


@router.post("/register", response_model=RunnerRegistrationRead, status_code=status.HTTP_201_CREATED)
def post_register(request: Request, payload: RunnerRegister, db: Session = Depends(get_db)) -> RunnerRegistrationRead | JSONResponse:
    if payload.runner_id is None:
        denied = runner_enrollment_error(request)
        if denied is not None:
            return denied
    runner, enrollment_token = register_runner(
        db,
        name=payload.name,
        hostname=payload.hostname,
        platform=payload.platform,
        capabilities=payload.capabilities,
        metadata=payload.metadata,
        runner_id=payload.runner_id,
        runner_token=payload.runner_token,
    )
    return RunnerRegistrationRead(
        **to_read(runner, offline_after_seconds=_settings().runner_offline_seconds),
        enrollment_token=enrollment_token,
    )


@router.post("/{runner_id}/heartbeat", response_model=RunnerRead)
def post_heartbeat(runner_id: str, payload: RunnerHeartbeat, runner_token: str | None = Depends(_runner_token), db: Session = Depends(get_db)) -> RunnerRead:
    authenticate_runner(db, runner_id, runner_token)
    runner = heartbeat_runner(
        db,
        runner_id,
        hostname=payload.hostname,
        platform=payload.platform,
        capabilities=payload.capabilities,
        metadata=payload.metadata,
        lease_seconds=_settings().worker_lease_seconds,
    )
    return RunnerRead(**to_read(runner, offline_after_seconds=_settings().runner_offline_seconds))


@router.post("/{runner_id}/claim", response_model=RunnerClaimRead | None)
def post_claim(runner_id: str, runner_token: str | None = Depends(_runner_token), db: Session = Depends(get_db)) -> RunnerClaimRead | None:
    runner = authenticate_runner(db, runner_id, runner_token)
    if runner.status == RunnerStatus.DISABLED.value:
        raise RelayviaError("RUNNER_DISABLED", "Runner is disabled", status_code=409)
    if not runner_online(runner, offline_after_seconds=_settings().runner_offline_seconds):
        raise RelayviaError("RUNNER_OFFLINE", "Runner must heartbeat before claiming work", status_code=409)
    task = runner_claim(db, runner, lease_seconds=_settings().worker_lease_seconds)
    if task is None:
        return None
    payload = task.payload_json or {}
    return RunnerClaimRead(
        task_id=task.id,
        workflow_run_id=task.workflow_run_id,
        node_run_id=task.node_run_id,
        node_id=payload.get("node_id"),
        execution_type=payload.get("execution_type"),
        config=payload.get("config"),
        workspace=payload.get("workspace"),
        attempt=task.attempt,
        lease_token=task.lease_token or "",
    )


@router.post("/{runner_id}/tasks/{task_id}/heartbeat", response_model=RunnerTaskHeartbeatRead)
def post_task_heartbeat(
    runner_id: str,
    task_id: str,
    lease_token: str,
    runner_token: str | None = Depends(_runner_token),
    db: Session = Depends(get_db),
) -> RunnerTaskHeartbeatRead:
    runner = authenticate_runner(db, runner_id, runner_token)
    return RunnerTaskHeartbeatRead(
        cancel_requested=runner_task_heartbeat(
            db,
            runner=runner,
            task_id=task_id,
            lease_token=lease_token,
            lease_seconds=_settings().worker_lease_seconds,
        )
    )


@router.post("/{runner_id}/submit-result", response_model=RunnerRead)
def post_submit_result(runner_id: str, payload: RunnerSubmitRequest, runner_token: str | None = Depends(_runner_token), db: Session = Depends(get_db)) -> RunnerRead:
    authenticate_runner(db, runner_id, runner_token)
    ok = runner_submit(
        db,
        runner_id=runner_id,
        task_id=payload.task_id,
        lease_token=payload.lease_token,
        result=payload.result.model_dump(),
        storage=get_artifact_storage(),
        max_bytes=_settings().artifact_max_bytes,
    )
    if not ok:
        raise RelayviaError(
            "RUNNER_TASK_STALE",
            "Task is no longer owned by this Runner (expired lease or already completed)",
            status_code=409,
        )
    runner = get_runner(db, runner_id, offline_after_seconds=_settings().runner_offline_seconds)
    return RunnerRead(**to_read(runner, offline_after_seconds=_settings().runner_offline_seconds))


@router.post("/{runner_id}/workspace-cleanups/claim", response_model=RunnerWorkspaceCleanupClaim | None)
def post_workspace_cleanup_claim(runner_id: str, runner_token: str | None = Depends(_runner_token), db: Session = Depends(get_db)) -> RunnerWorkspaceCleanupClaim | None:
    runner = authenticate_runner(db, runner_id, runner_token)
    if runner.status == RunnerStatus.DISABLED.value:
        raise RelayviaError("RUNNER_DISABLED", "Runner is disabled", status_code=409)
    workspace = claim_workspace_cleanup(db, runner, stale_after_seconds=_settings().worker_lease_seconds)
    if workspace is None or not workspace.path:
        return None
    return RunnerWorkspaceCleanupClaim(
        workspace_id=workspace.id,
        repository=workspace.repository,
        path=workspace.path,
        branch=workspace.branch,
        strategy=workspace.workspace_type,
    )


@router.post("/{runner_id}/workspace-cleanups/{workspace_id}/complete", response_model=RunnerRead)
def post_workspace_cleanup_complete(runner_id: str, workspace_id: str, payload: RunnerWorkspaceCleanupResult, runner_token: str | None = Depends(_runner_token), db: Session = Depends(get_db)) -> RunnerRead:
    runner = authenticate_runner(db, runner_id, runner_token)
    complete_workspace_cleanup(db, runner, workspace_id, ok=payload.ok, error=payload.error)
    return RunnerRead(**to_read(runner, offline_after_seconds=_settings().runner_offline_seconds))


@router.post("/{runner_id}/artifact-uploads", response_model=RunnerArtifactUploadRead, status_code=status.HTTP_201_CREATED)
def post_artifact_upload(runner_id: str, payload: RunnerArtifactUploadCreate, runner_token: str | None = Depends(_runner_token), db: Session = Depends(get_db)) -> RunnerArtifactUploadRead:
    authenticate_runner(db, runner_id, runner_token)
    artifact = create_runner_artifact_upload(
        db,
        runner_id=runner_id,
        task_id=payload.task_id,
        lease_token=payload.lease_token,
        name=payload.name,
        artifact_type=payload.type,
        content_type=payload.content_type,
        metadata=payload.metadata,
        output_key=payload.output_key,
    )
    return RunnerArtifactUploadRead(artifact_id=artifact.id, uri=artifact.uri)


@router.post("/{runner_id}/artifact-uploads/{artifact_id}/content", response_model=RunnerArtifactUploadRead)
async def post_artifact_upload_content(
    runner_id: str,
    artifact_id: str,
    request: Request,
    task_id: str = Header(alias="X-Relayvia-Task-Id"),
    lease_token: str = Header(alias="X-Relayvia-Lease-Token"),
    runner_token: str | None = Depends(_runner_token),
    db: Session = Depends(get_db),
) -> RunnerArtifactUploadRead:
    authenticate_runner(db, runner_id, runner_token)
    artifact = validate_runner_artifact_upload(
        db,
        artifact_id=artifact_id,
        runner_id=runner_id,
        task_id=task_id,
        lease_token=lease_token,
    )
    maximum = _settings().artifact_max_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > maximum:
        fail_runner_artifact_upload(db, artifact, error="artifact exceeds configured size limit")
        raise RelayviaError("ARTIFACT_TOO_LARGE", "Artifact content exceeds the configured size limit", status_code=413, details={"max_bytes": maximum})
    storage = get_artifact_storage()
    size = 0
    try:
        with SpooledTemporaryFile(max_size=min(maximum, 4 * 1024 * 1024)) as stream:
            async for chunk in request.stream():
                size += len(chunk)
                if size > maximum:
                    raise RelayviaError("ARTIFACT_TOO_LARGE", "Artifact content exceeds the configured size limit", status_code=413, details={"max_bytes": maximum})
                stream.write(chunk)
            stream.seek(0)
            stored_size = storage.save_stream(artifact.id, stream)
        finalize_runner_artifact_upload(db, artifact, size=stored_size)
    except Exception as exc:
        db.rollback()
        try:
            storage.delete(artifact.id)
        except Exception:
            pass
        artifact = db.get(type(artifact), artifact_id)
        if artifact is None:
            raise
        if not isinstance(exc, RelayviaError):
            fail_runner_artifact_upload(db, artifact, error="artifact storage failed")
        else:
            fail_runner_artifact_upload(db, artifact, error=exc.message)
        raise
    return RunnerArtifactUploadRead(artifact_id=artifact.id, uri=artifact.uri)
