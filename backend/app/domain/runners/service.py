"""Relayvia Runner service: registration, heartbeat, claim, result.

Runners are pull-based: they register a stable identity, heartbeat to stay
ONLINE, claim capability-matched tasks, execute locally, and submit results.
Runners never parse the Graph, never schedule, and never mutate Workflow
state beyond reporting an ExecutionResult.
"""

from datetime import timedelta, timezone
import base64
import hashlib
import hmac
import secrets
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.errors import RelayviaError
from app.domain.execution.models import ExecutionTask
from app.domain.execution.state_machine import ExecutionTaskStatus, transition_execution_task
from app.domain.runners.models import Runner, RunnerStatus, runner_online
from app.domain.runs.events import RunEventType, record_event
from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.runs.repository import list_node_runs
from app.domain.artifacts.service import register_artifact_candidates
from app.domain.workspaces.models import Workspace, WorkspaceStatus
from app.infrastructure.artifact_storage.base import ArtifactStorage
from app.infrastructure.database.base import utc_now
from app.runtime.scheduler.workflow_scheduler import WorkflowScheduler
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus, transition_node_run
from app.runtime.executor.trace import sanitize_error, sanitize_metadata


def get_runner(db: Session, runner_id: str, *, offline_after_seconds: int) -> Runner:
    runner = db.get(Runner, runner_id)
    if runner is None:
        raise RelayviaError("RUNNER_NOT_FOUND", "Runner not found", status_code=404)
    return runner


def _effective_status(runner: Runner, *, offline_after_seconds: int) -> str:
    if runner.status == RunnerStatus.DISABLED.value:
        return RunnerStatus.DISABLED.value
    return RunnerStatus.ONLINE.value if runner_online(runner, offline_after_seconds=offline_after_seconds) else RunnerStatus.OFFLINE.value


def to_read(runner: Runner, *, offline_after_seconds: int) -> dict:
    return {
        "id": runner.id,
        "name": runner.name,
        "hostname": runner.hostname,
        "platform": runner.platform,
        "status": _effective_status(runner, offline_after_seconds=offline_after_seconds),
        "capabilities": runner.capabilities_json,
        "last_seen_at": runner.last_seen_at,
        "metadata": runner.metadata_json,
        "created_at": runner.created_at,
        "updated_at": runner.updated_at,
    }


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def authenticate_runner(db: Session, runner_id: str, runner_token: str | None) -> Runner:
    """Authenticate a Runner mutating the control plane.

    Runner IDs identify a machine but are deliberately not credentials. Every
    heartbeat, claim and result submission is token-fenced to prevent another
    host from impersonating that machine.
    """
    runner = db.get(Runner, runner_id)
    if runner is None:
        raise RelayviaError("RUNNER_NOT_FOUND", "Runner not found", status_code=404)
    expected = runner.auth_token_hash
    if not runner_token or not expected or not hmac.compare_digest(_token_hash(runner_token), expected):
        raise RelayviaError("RUNNER_AUTH_FAILED", "Runner authentication failed", status_code=401)
    return runner


def register_runner(
    db: Session,
    *,
    name: str,
    hostname: str,
    platform: str | None,
    capabilities: list[str],
    metadata: dict,
    runner_id: str | None,
    runner_token: str | None,
) -> tuple[Runner, str | None]:
    enrollment_token: str | None = None
    if runner_id:
        runner = authenticate_runner(db, runner_id, runner_token)
    else:
        enrollment_token = secrets.token_urlsafe(32)
        runner = Runner(
            id=str(uuid4()),
            name=name,
            hostname=hostname,
            platform=platform,
            auth_token_hash=_token_hash(enrollment_token),
            capabilities_json=capabilities,
            metadata_json=metadata,
        )
        db.add(runner)
    runner.name = name
    runner.hostname = hostname
    runner.platform = platform
    runner.capabilities_json = capabilities
    runner.metadata_json = metadata or {}
    runner.status = RunnerStatus.ONLINE.value
    runner.last_seen_at = utc_now()
    db.commit()
    db.refresh(runner)
    return runner, enrollment_token


def heartbeat_runner(db: Session, runner_id: str, *, hostname: str, platform: str | None, capabilities: list[str], metadata: dict, lease_seconds: int) -> Runner:
    runner = db.get(Runner, runner_id)
    if runner is None:
        raise RelayviaError("RUNNER_NOT_FOUND", "Runner not found", status_code=404)
    if runner.status == RunnerStatus.DISABLED.value:
        raise RelayviaError("RUNNER_DISABLED", "Runner is disabled", status_code=409)
    runner.hostname = hostname
    runner.platform = platform
    runner.capabilities_json = capabilities
    runner.metadata_json = metadata or {}
    runner.status = RunnerStatus.ONLINE.value
    runner.last_seen_at = utc_now()
    # Renew leases of RUNNING tasks owned by this Runner so long executions
    # stay owned while the Runner is alive.
    db.execute(
        update(ExecutionTask)
        .where(
            ExecutionTask.locked_by == runner_id,
            ExecutionTask.status == ExecutionTaskStatus.RUNNING.value,
        )
        .values(lease_expires_at=utc_now() + timedelta(seconds=lease_seconds))
    )
    db.commit()
    db.refresh(runner)
    return runner


def runner_claim(db: Session, runner: Runner, *, lease_seconds: int) -> ExecutionTask | None:
    capabilities = set(runner.capabilities_json)
    now = utc_now()
    task = db.scalar(
        select(ExecutionTask)
        .join(WorkflowRun, WorkflowRun.id == ExecutionTask.workflow_run_id)
        .where(
            ExecutionTask.status == ExecutionTaskStatus.PENDING.value,
            ExecutionTask.available_at <= now,
            WorkflowRun.status == WorkflowRunStatus.RUNNING.value,
            ExecutionTask.required_capability.in_(capabilities),
            or_(ExecutionTask.runner_id.is_(None), ExecutionTask.runner_id == runner.id),
        )
        .order_by(ExecutionTask.priority.desc(), ExecutionTask.available_at.asc(), ExecutionTask.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if task is None:
        return None

    lease_token = str(uuid4())
    claimed = (
        update(ExecutionTask)
        .where(ExecutionTask.id == task.id, ExecutionTask.status == ExecutionTaskStatus.PENDING.value)
        .values(
            status=ExecutionTaskStatus.CLAIMED.value,
            locked_by=runner.id,
            lease_token=lease_token,
            locked_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
        )
    )
    if db.execute(claimed).rowcount != 1:
        db.rollback()
        return None

    task.status = ExecutionTaskStatus.CLAIMED.value
    transition_execution_task(ExecutionTaskStatus(task.status), ExecutionTaskStatus.RUNNING)
    task.status = ExecutionTaskStatus.RUNNING.value
    task.attempt += 1
    task.started_at = now
    node_run = db.get(NodeRun, task.node_run_id)
    if node_run is not None:
        if NodeRunStatus(node_run.status) is not NodeRunStatus.RUNNING:
            transition_node_run(NodeRunStatus(node_run.status), NodeRunStatus.RUNNING)
            node_run.status = NodeRunStatus.RUNNING.value
    payload = task.payload_json if isinstance(task.payload_json, dict) else {}
    workspace_ref = payload.get("workspace")
    if isinstance(workspace_ref, dict) and isinstance(workspace_ref.get("id"), str):
        workspace = db.get(Workspace, workspace_ref["id"])
        if workspace is not None:
            workspace.runner_id = runner.id
            workspace.status = WorkspaceStatus.IN_USE.value
    record_event(
        db,
        workflow_run_id=task.workflow_run_id,
        node_run_id=task.node_run_id,
        event_type=RunEventType.NODE_STARTED,
        message=f"Node started on Runner {runner.name} (attempt {task.attempt})",
        payload={
            "node_id": task.payload_json.get("node_id") if isinstance(task.payload_json, dict) else None,
            "runner_id": runner.id,
            "attempt": task.attempt,
        },
    )
    db.commit()
    db.refresh(task)
    return task


def _owns(task: ExecutionTask, runner_id: str, lease_token: str) -> bool:
    if task is None or task.status in (ExecutionTaskStatus.COMPLETED.value, ExecutionTaskStatus.FAILED.value, ExecutionTaskStatus.CANCELLED.value):
        return False
    return (
        task.locked_by == runner_id
        and task.lease_token == lease_token
        and task.lease_expires_at is not None
        and _lease_active(task.lease_expires_at)
    )


def _lease_active(expires_at) -> bool:
    expires = expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at
    return expires > utc_now()


def runner_submit(
    db: Session,
    *,
    runner_id: str,
    task_id: str,
    lease_token: str,
    result: dict,
    storage: ArtifactStorage,
    max_bytes: int,
) -> bool:
    task = db.scalar(select(ExecutionTask).where(ExecutionTask.id == task_id).with_for_update())
    if not _owns(task, runner_id, lease_token):
        return False

    raw_error = result.get("error") or {
        "code": "RUNNER_EXECUTION_FAILED",
        "message": "Runner execution failed",
        "retryable": False,
        "details": {},
    }
    error = sanitize_error(raw_error if isinstance(raw_error, dict) else {"code": "RUNNER_EXECUTION_FAILED", "message": "Runner execution failed"})
    should_retry = not result.get("ok") and bool(error.get("retryable")) and task.attempt < task.max_attempts

    references: list[dict] = []
    output_map: dict[str, str] = {}
    # A retry has not produced a durable node result yet. Avoid registering
    # transient artifacts that would otherwise become orphaned.
    if result.get("artifacts") and not should_retry:
        # Artifact `content` travels base64-encoded over the JSON API.
        artifacts: list[dict] = []
        for item in result["artifacts"]:
            if isinstance(item, dict) and isinstance(item.get("content"), str):
                try:
                    item = {**item, "content": base64.b64decode(item["content"])}
                except (ValueError, TypeError):
                    raise RelayviaError("INVALID_ARTIFACT_CONTENT", "Artifact content is not valid base64", status_code=422)
            artifacts.append(item)
        references, output_map = register_artifact_candidates(
            db,
            workflow_run_id=task.workflow_run_id,
            producer_node_run_id=task.node_run_id,
            candidates=artifacts,
            storage=storage,
            max_bytes=max_bytes,
        )

    output = {**(result.get("output") or {}), **output_map}
    if result.get("ok"):
        transition_execution_task(ExecutionTaskStatus(task.status), ExecutionTaskStatus.COMPLETED)
        task.status = ExecutionTaskStatus.COMPLETED.value
        task.finished_at = utc_now()
        task.last_error_json = None
        node_run = db.get(NodeRun, task.node_run_id)
        if node_run is not None:
            transition_node_run(NodeRunStatus(node_run.status), NodeRunStatus.COMPLETED)
            node_run.status = NodeRunStatus.COMPLETED.value
            node_run.output_json = output
            node_run.execution_metadata_json = sanitize_metadata(result.get("metadata") or {})
            node_run.artifact_refs_json = references
            node_run.finished_at = utc_now()
        record_event(
            db,
            workflow_run_id=task.workflow_run_id,
            node_run_id=task.node_run_id,
            event_type=RunEventType.NODE_COMPLETED,
            message="Node completed on Runner",
            payload={"node_id": task.payload_json.get("node_id") if isinstance(task.payload_json, dict) else None, "runner_id": runner_id},
        )
    elif should_retry:
        backoff_seconds = _retry_backoff_seconds(task.payload_json)
        transition_execution_task(ExecutionTaskStatus(task.status), ExecutionTaskStatus.RETRY_WAIT)
        task.status = ExecutionTaskStatus.RETRY_WAIT.value
        task.available_at = utc_now() + timedelta(seconds=backoff_seconds)
        task.locked_by = None
        task.lease_token = None
        task.locked_at = None
        task.lease_expires_at = None
        task.last_error_json = error
        node_run = db.get(NodeRun, task.node_run_id)
        if node_run is not None and NodeRunStatus(node_run.status) is not NodeRunStatus.RETRYING:
            transition_node_run(NodeRunStatus(node_run.status), NodeRunStatus.RETRYING)
            node_run.status = NodeRunStatus.RETRYING.value
        record_event(
            db,
            workflow_run_id=task.workflow_run_id,
            node_run_id=task.node_run_id,
            event_type=RunEventType.NODE_RETRYING,
            message=f"Runner execution retrying in {backoff_seconds}s",
            payload={"node_id": task.payload_json.get("node_id") if isinstance(task.payload_json, dict) else None, "runner_id": runner_id, "attempt": task.attempt, "backoff_seconds": backoff_seconds},
        )
    else:
        transition_execution_task(ExecutionTaskStatus(task.status), ExecutionTaskStatus.FAILED)
        task.status = ExecutionTaskStatus.FAILED.value
        task.finished_at = utc_now()
        task.last_error_json = error
        node_run = db.get(NodeRun, task.node_run_id)
        if node_run is not None and NodeRunStatus(node_run.status) is not NodeRunStatus.FAILED:
            transition_node_run(NodeRunStatus(node_run.status), NodeRunStatus.FAILED)
            node_run.status = NodeRunStatus.FAILED.value
            node_run.error_json = error
            node_run.execution_metadata_json = sanitize_metadata(result.get("metadata") or {})
            node_run.artifact_refs_json = references
            node_run.finished_at = utc_now()
        record_event(
            db,
            workflow_run_id=task.workflow_run_id,
            node_run_id=task.node_run_id,
            event_type=RunEventType.NODE_FAILED,
            message=error.get("message") if isinstance(error, dict) else None,
            payload={"node_id": task.payload_json.get("node_id") if isinstance(task.payload_json, dict) else None, "runner_id": runner_id, "error_code": error.get("code") if isinstance(error, dict) else None},
        )
    if not should_retry:
        _sync_workspace_result(db, task, result)
    db.commit()
    if not should_retry:
        WorkflowScheduler().reconcile_run(db, task.workflow_run_id)
        db.commit()
    return True


def _retry_backoff_seconds(payload: object) -> int:
    try:
        return max(0, min(int((payload or {}).get("retry_backoff_seconds", 5)), 86_400))
    except (AttributeError, TypeError, ValueError):
        return 5


def _sync_workspace_result(db: Session, task: ExecutionTask, result: dict) -> None:
    payload = task.payload_json if isinstance(task.payload_json, dict) else {}
    workspace_ref = payload.get("workspace")
    if not isinstance(workspace_ref, dict) or not workspace_ref.get("id"):
        return
    workspace = db.get(Workspace, workspace_ref["id"])
    if workspace is None:
        return
    metadata = result.get("metadata") or {}
    if metadata.get("workspace_path"):
        workspace.path = str(metadata["workspace_path"])
    if metadata.get("workspace_branch"):
        workspace.branch = str(metadata["workspace_branch"])
    workspace.status = (WorkspaceStatus.RELEASED if result.get("ok") else WorkspaceStatus.FAILED).value
