"""ExecutionTask query service (read-only debug surface)."""

from sqlalchemy.orm import Session

from app.core.errors import RelayviaError
from app.domain.execution.models import ExecutionTask
from app.domain.execution.repository import list_tasks_for_run
from app.domain.execution.schemas import ExecutionTaskRead
from app.domain.execution.state_machine import ExecutionTaskStatus
from app.domain.runs.repository import get_run


def list_execution_tasks(db: Session, run_id: str) -> list[ExecutionTaskRead]:
    if get_run(db, run_id) is None:
        raise RelayviaError("WORKFLOW_RUN_NOT_FOUND", "Workflow Run not found", status_code=404)
    tasks = list_tasks_for_run(db, run_id)
    return [
        ExecutionTaskRead(
            id=task.id,
            workflow_run_id=task.workflow_run_id,
            node_run_id=task.node_run_id,
            task_type=task.task_type,
            status=ExecutionTaskStatus(task.status),
            payload=task.payload_json,
            priority=task.priority,
            attempt=task.attempt,
            max_attempts=task.max_attempts,
            available_at=task.available_at,
            locked_by=task.locked_by,
            locked_at=task.locked_at,
            lease_expires_at=task.lease_expires_at,
            execution_key=task.execution_key,
            last_error=task.last_error_json,
            started_at=task.started_at,
            finished_at=task.finished_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
        for task in tasks
    ]
