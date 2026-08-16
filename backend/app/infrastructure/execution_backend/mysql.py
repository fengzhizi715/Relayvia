"""MySQL-backed ExecutionBackend.

Claim uses `SELECT ... FOR UPDATE SKIP LOCKED` (MySQL 8) inside a short
transaction, followed by a conditional `WHERE status = pending` UPDATE so the
invariant "one task, one owner" also holds on dialects without row locks
(e.g. SQLite in tests). Lease token fencing guards every write.
"""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.domain.execution.models import ExecutionTask
from app.domain.execution.state_machine import ExecutionTaskStatus, is_execution_task_terminal, transition_execution_task
from app.domain.runs.models import NodeRun, WorkflowRun
from app.infrastructure.database.base import utc_now
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus, is_node_run_terminal, transition_node_run
from .base import ClaimedTask, ExecutionBackend


class MySQLExecutionBackend(ExecutionBackend):
    def __init__(self, session_factory: sessionmaker[Session], *, lease_seconds: int = 60) -> None:
        self._session_factory = session_factory
        self.lease_seconds = lease_seconds

    async def submit(self, workflow_run_id: str, node_run_id: str, *, payload: dict, priority: int, max_attempts: int, available_at) -> str:
        with self._session_factory() as db:
            task = ExecutionTask(
                workflow_run_id=workflow_run_id,
                node_run_id=node_run_id,
                task_type="node_execution",
                status=ExecutionTaskStatus.PENDING.value,
                payload_json=payload,
                priority=priority,
                attempt=0,
                max_attempts=max_attempts,
                available_at=available_at,
                execution_key=f"{workflow_run_id}:{node_run_id}",
            )
            db.add(task)
            db.commit()
            return task.id

    async def claim(self, worker_id: str) -> ClaimedTask | None:
        with self._session_factory() as db:
            now = utc_now()
            task = db.scalar(
                select(ExecutionTask)
                .join(WorkflowRun, WorkflowRun.id == ExecutionTask.workflow_run_id)
                .where(
                    ExecutionTask.status == ExecutionTaskStatus.PENDING.value,
                    ExecutionTask.available_at <= now,
                    WorkflowRun.status == WorkflowRunStatus.RUNNING.value,
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
                    locked_by=worker_id,
                    lease_token=lease_token,
                    locked_at=now,
                    lease_expires_at=now + timedelta(seconds=self.lease_seconds),
                )
            )
            result = db.execute(claimed)
            if result.rowcount != 1:
                db.rollback()
                return None
            db.commit()
            return ClaimedTask(
                id=task.id,
                workflow_run_id=task.workflow_run_id,
                node_run_id=task.node_run_id,
                task_type=task.task_type,
                payload=task.payload_json,
                attempt=task.attempt,
                max_attempts=task.max_attempts,
                execution_key=task.execution_key,
                locked_by=worker_id,
                lease_token=lease_token,
                lease_expires_at=now + timedelta(seconds=self.lease_seconds),
            )

    async def start(self, task_id: str, worker_id: str, lease_token: str) -> bool:
        with self._session_factory() as db:
            task = db.scalar(select(ExecutionTask).where(ExecutionTask.id == task_id).with_for_update())
            if not self._owns(db, task, worker_id, lease_token):
                return False
            run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == task.workflow_run_id).with_for_update())
            if run is None or WorkflowRunStatus(run.status) is not WorkflowRunStatus.RUNNING:
                self._release_or_cancel_for_run_state(db, task, run)
                db.commit()
                return False
            transition_execution_task(ExecutionTaskStatus(task.status), ExecutionTaskStatus.RUNNING)
            task.status = ExecutionTaskStatus.RUNNING.value
            task.attempt += 1
            task.started_at = utc_now()
            self._node_status(db, task.node_run_id, target=NodeRunStatus.RUNNING, allow_same=True)
            db.commit()
            return True

    async def complete(self, task_id: str, worker_id: str, lease_token: str, output: dict) -> bool:
        with self._session_factory() as db:
            task = db.scalar(select(ExecutionTask).where(ExecutionTask.id == task_id).with_for_update())
            if not self._owns(db, task, worker_id, lease_token):
                return False
            transition_execution_task(ExecutionTaskStatus(task.status), ExecutionTaskStatus.COMPLETED)
            task.status = ExecutionTaskStatus.COMPLETED.value
            task.finished_at = utc_now()
            task.last_error_json = None
            self._node_completed(db, task.node_run_id, output)
            db.commit()
            return True

    async def fail(self, task_id: str, worker_id: str, lease_token: str, error: dict) -> bool:
        with self._session_factory() as db:
            task = db.scalar(select(ExecutionTask).where(ExecutionTask.id == task_id).with_for_update())
            if not self._owns(db, task, worker_id, lease_token):
                return False
            transition_execution_task(ExecutionTaskStatus(task.status), ExecutionTaskStatus.FAILED)
            task.status = ExecutionTaskStatus.FAILED.value
            task.finished_at = utc_now()
            task.last_error_json = error
            self._node_failed(db, task.node_run_id, error)
            db.commit()
            return True

    async def schedule_retry(self, task_id: str, worker_id: str, lease_token: str, backoff_seconds: int) -> bool:
        with self._session_factory() as db:
            task = db.scalar(select(ExecutionTask).where(ExecutionTask.id == task_id).with_for_update())
            if not self._owns(db, task, worker_id, lease_token):
                return False
            transition_execution_task(ExecutionTaskStatus(task.status), ExecutionTaskStatus.RETRY_WAIT)
            task.status = ExecutionTaskStatus.RETRY_WAIT.value
            task.available_at = utc_now() + timedelta(seconds=backoff_seconds)
            task.locked_by = None
            task.lease_token = None
            task.locked_at = None
            task.lease_expires_at = None
            task.last_error_json = task.last_error_json
            self._node_status(db, task.node_run_id, target=NodeRunStatus.RETRYING, allow_same=True)
            db.commit()
            return True

    async def renew_lease(self, task_id: str, worker_id: str, lease_token: str) -> bool:
        with self._session_factory() as db:
            task = db.scalar(select(ExecutionTask).where(ExecutionTask.id == task_id).with_for_update())
            if not self._owns(db, task, worker_id, lease_token):
                return False
            task.lease_expires_at = utc_now() + timedelta(seconds=self.lease_seconds)
            db.commit()
            return True

    async def cancel(self, task_id: str) -> bool:
        with self._session_factory() as db:
            task = db.scalar(select(ExecutionTask).where(ExecutionTask.id == task_id).with_for_update())
            if task is None or is_execution_task_terminal(ExecutionTaskStatus(task.status)):
                return False
            transition_execution_task(ExecutionTaskStatus(task.status), ExecutionTaskStatus.CANCELLED)
            task.status = ExecutionTaskStatus.CANCELLED.value
            task.finished_at = utc_now()
            self._node_cancelled(db, task.node_run_id)
            db.commit()
            return True

    async def recover_expired(self) -> int:
        with self._session_factory() as db:
            now = utc_now()
            tasks = db.scalars(
                select(ExecutionTask)
                .where(
                    ExecutionTask.status.in_([ExecutionTaskStatus.CLAIMED.value, ExecutionTaskStatus.RUNNING.value]),
                    ExecutionTask.lease_expires_at < now,
                )
                .with_for_update(skip_locked=True)
            ).all()
            count = 0
            for task in tasks:
                transition_execution_task(ExecutionTaskStatus(task.status), ExecutionTaskStatus.PENDING)
                task.status = ExecutionTaskStatus.PENDING.value
                task.locked_by = None
                task.lease_token = None
                task.locked_at = None
                task.lease_expires_at = None
                count += 1
            db.commit()
            return count

    async def promote_due_retries(self) -> int:
        with self._session_factory() as db:
            now = utc_now()
            tasks = db.scalars(
                select(ExecutionTask)
                .where(ExecutionTask.status == ExecutionTaskStatus.RETRY_WAIT.value, ExecutionTask.available_at <= now)
                .with_for_update(skip_locked=True)
            ).all()
            count = 0
            for task in tasks:
                transition_execution_task(ExecutionTaskStatus(task.status), ExecutionTaskStatus.PENDING)
                task.status = ExecutionTaskStatus.PENDING.value
                self._node_status(db, task.node_run_id, target=NodeRunStatus.QUEUED, allow_same=True)
                count += 1
            db.commit()
            return count

    # --- helpers ---

    @staticmethod
    def _owns(db: Session, task: ExecutionTask | None, worker_id: str, lease_token: str) -> bool:
        if task is None:
            return False
        if is_execution_task_terminal(ExecutionTaskStatus(task.status)):
            return False
        return task.locked_by == worker_id and task.lease_token == lease_token

    @staticmethod
    def _release_or_cancel_for_run_state(db: Session, task: ExecutionTask, run: WorkflowRun | None) -> None:
        """A claimed task must not start after pause/wait/terminal transition.

        Paused and waiting runs retain their queued work for resume. Terminal
        runs cancel it, which also fences a worker that raced with fail-fast
        reconciliation.
        """
        status = WorkflowRunStatus(run.status) if run is not None else WorkflowRunStatus.CANCELLED
        if status in {WorkflowRunStatus.PAUSED, WorkflowRunStatus.WAITING}:
            transition_execution_task(ExecutionTaskStatus(task.status), ExecutionTaskStatus.PENDING)
            task.status = ExecutionTaskStatus.PENDING.value
            task.locked_by = None
            task.lease_token = None
            task.locked_at = None
            task.lease_expires_at = None
            return
        transition_execution_task(ExecutionTaskStatus(task.status), ExecutionTaskStatus.CANCELLED)
        task.status = ExecutionTaskStatus.CANCELLED.value
        task.finished_at = utc_now()
        MySQLExecutionBackend._node_cancelled(db, task.node_run_id)

    @staticmethod
    def _node_status(db: Session, node_run_id: str, *, target: NodeRunStatus, allow_same: bool) -> None:
        node_run = db.get(NodeRun, node_run_id)
        if node_run is None:
            return
        current = NodeRunStatus(node_run.status)
        if allow_same and current is target:
            return
        transition_node_run(current, target)
        node_run.status = target.value

    @staticmethod
    def _node_completed(db: Session, node_run_id: str, output: dict) -> None:
        node_run = db.get(NodeRun, node_run_id)
        if node_run is None:
            return
        transition_node_run(NodeRunStatus(node_run.status), NodeRunStatus.COMPLETED)
        node_run.status = NodeRunStatus.COMPLETED.value
        node_run.output_json = output
        node_run.finished_at = utc_now()

    @staticmethod
    def _node_failed(db: Session, node_run_id: str, error: dict) -> None:
        node_run = db.get(NodeRun, node_run_id)
        if node_run is None:
            return
        current = NodeRunStatus(node_run.status)
        if not is_node_run_terminal(current):
            transition_node_run(current, NodeRunStatus.FAILED)
            node_run.status = NodeRunStatus.FAILED.value
            node_run.error_json = error
            node_run.finished_at = utc_now()

    @staticmethod
    def _node_cancelled(db: Session, node_run_id: str) -> None:
        node_run = db.get(NodeRun, node_run_id)
        if node_run is None:
            return
        current = NodeRunStatus(node_run.status)
        if not is_node_run_terminal(current):
            transition_node_run(current, NodeRunStatus.CANCELLED)
            node_run.status = NodeRunStatus.CANCELLED.value
            node_run.finished_at = utc_now()
