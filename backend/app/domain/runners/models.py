"""Relayvia Runner persistent model.

A Runner is an independently started local execution component (workstation /
edge / GPU host). It pulls tasks from the backend and executes local
capabilities (shell / git / local process). It never parses the Workflow
Graph, never schedules nodes and never mutates Workflow state.
"""

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, utc_now


class RunnerStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    DISABLED = "disabled"


class Runner(TimestampMixin, Base):
    __tablename__ = "runners"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RunnerStatus.OFFLINE.value, index=True)
    # A Runner token is generated during first enrollment.  Only its SHA-256
    # digest is persisted; the raw token is returned exactly once.
    auth_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    capabilities_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def runner_online(runner: Runner, *, offline_after_seconds: int, now: datetime | None = None) -> bool:
    if runner.status == RunnerStatus.DISABLED.value:
        return False
    if runner.last_seen_at is None:
        return False
    now = _aware(now or utc_now())
    return (_aware(runner.last_seen_at) - now).total_seconds() > -offline_after_seconds


__all__ = ["Runner", "RunnerStatus", "runner_online"]
