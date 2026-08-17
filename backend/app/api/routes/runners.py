from fastapi import APIRouter, Depends, Header, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import RelayviaError
from app.domain.runners.schemas import (
    RunnerClaimRead,
    RunnerHeartbeat,
    RunnerRegistrationRead,
    RunnerRead,
    RunnerRegister,
    RunnerSubmitRequest,
)
from app.domain.runners.service import (
    get_runner,
    authenticate_runner,
    heartbeat_runner,
    register_runner,
    runner_claim,
    runner_submit,
    to_read,
)
from app.domain.runners.models import Runner, RunnerStatus, runner_online
from app.infrastructure.artifact_storage import get_artifact_storage
from app.infrastructure.database.session import get_db

router = APIRouter(prefix="/runners", tags=["runners"])


def _settings():
    return get_settings()


@router.get("", response_model=list[RunnerRead])
def get_runners(db: Session = Depends(get_db)) -> list[RunnerRead]:
    runners = db.scalars(select(Runner).order_by(Runner.name)).all()
    offline_after = _settings().runner_offline_seconds
    return [RunnerRead(**to_read(runner, offline_after_seconds=offline_after)) for runner in runners]


@router.get("/{runner_id}", response_model=RunnerRead)
def get_runner_detail(runner_id: str, db: Session = Depends(get_db)) -> RunnerRead:
    runner = get_runner(db, runner_id, offline_after_seconds=_settings().runner_offline_seconds)
    return RunnerRead(**to_read(runner, offline_after_seconds=_settings().runner_offline_seconds))


def _runner_token(x_relayvia_runner_token: str | None = Header(default=None)) -> str | None:
    return x_relayvia_runner_token


@router.post("/register", response_model=RunnerRegistrationRead, status_code=status.HTTP_201_CREATED)
def post_register(payload: RunnerRegister, db: Session = Depends(get_db)) -> RunnerRegistrationRead:
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
