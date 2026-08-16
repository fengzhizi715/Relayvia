"""ExecutionBackend abstraction.

The Workflow Runtime / Worker depend on this interface, never on MySQL
details (SKIP LOCKED, leases, etc.). V1 ships `MySQLExecutionBackend`; a
Redis/Temporal backend could be swapped in behind the same interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ClaimedTask:
    """A task claimed by a worker. Detached from any DB session."""

    id: str
    workflow_run_id: str
    node_run_id: str
    task_type: str
    payload: dict[str, Any]
    attempt: int
    max_attempts: int
    execution_key: str | None
    locked_by: str
    lease_token: str
    lease_expires_at: datetime
    error: dict[str, Any] | None = None


@dataclass(frozen=True)
class ExecutionErrorPayload:
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)


class ExecutionBackend(ABC):
    @abstractmethod
    async def submit(self, workflow_run_id: str, node_run_id: str, *, payload: dict[str, Any], priority: int, max_attempts: int, available_at: datetime) -> str:
        raise NotImplementedError

    @abstractmethod
    async def claim(self, worker_id: str) -> ClaimedTask | None:
        raise NotImplementedError

    @abstractmethod
    async def start(self, task_id: str, worker_id: str, lease_token: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def complete(
        self,
        task_id: str,
        worker_id: str,
        lease_token: str,
        output: dict[str, Any],
        *,
        execution_metadata: dict[str, Any] | None = None,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def fail(
        self,
        task_id: str,
        worker_id: str,
        lease_token: str,
        error: dict[str, Any],
        *,
        execution_metadata: dict[str, Any] | None = None,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def schedule_retry(self, task_id: str, worker_id: str, lease_token: str, backoff_seconds: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def renew_lease(self, task_id: str, worker_id: str, lease_token: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def cancel(self, task_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def recover_expired(self) -> int:
        raise NotImplementedError

    @abstractmethod
    async def promote_due_retries(self) -> int:
        raise NotImplementedError
