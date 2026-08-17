"""Run Trace API: event history (after_id pagination) and SSE stream."""

import asyncio
import json

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import RelayviaError
from app.domain.runs.events import RunEvent
from app.domain.runs.models import WorkflowRun
from app.domain.runs.repository import get_run
from app.infrastructure.database.session import get_db, get_session_factory
from app.runtime.state_machine import WorkflowRunStatus

router = APIRouter(prefix="/workflow-runs", tags=["runs"])


class RunEventRead(BaseModel):
    id: int
    workflow_run_id: str
    node_run_id: str | None
    event_type: str
    message: str | None
    payload: dict
    created_at: str


def _to_read(event: RunEvent) -> RunEventRead:
    return RunEventRead(
        id=event.id,
        workflow_run_id=event.workflow_run_id,
        node_run_id=event.node_run_id,
        event_type=event.event_type,
        message=event.message,
        payload=event.payload_json,
        created_at=event.created_at.isoformat() if event.created_at else "",
    )


def _ensure_run(db: Session, run_id: str) -> None:
    if get_run(db, run_id) is None:
        raise RelayviaError("WORKFLOW_RUN_NOT_FOUND", "Workflow Run not found", status_code=404)


@router.get("/{run_id}/events", response_model=list[RunEventRead])
def get_run_events(
    run_id: str,
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[RunEventRead]:
    _ensure_run(db, run_id)
    events = db.scalars(
        select(RunEvent)
        .where(RunEvent.workflow_run_id == run_id, RunEvent.id > after_id)
        .order_by(RunEvent.id)
        .limit(limit)
    ).all()
    return [_to_read(event) for event in events]


@router.get("/{run_id}/events/stream")
def stream_run_events(
    run_id: str,
    after_id: int | None = Query(default=None, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    """SSE stream of RunEvents. The database is the durable source of truth;
    this endpoint polls it and emits `id:`/`data:` frames so clients can
    resume with Last-Event-ID after a disconnect."""
    session_factory = get_session_factory()
    resume_after_id = after_id if after_id is not None else _parse_last_event_id(last_event_id)

    async def generator():
        last_id = resume_after_id
        while True:
            with session_factory() as db:
                run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
                if run is None:
                    yield "event: error\ndata: {\"code\":\"WORKFLOW_RUN_NOT_FOUND\"}\n\n"
                    return
                events = db.scalars(
                    select(RunEvent)
                    .where(RunEvent.workflow_run_id == run_id, RunEvent.id > last_id)
                    .order_by(RunEvent.id)
                    .limit(50)
                ).all()
                run_terminal = WorkflowRunStatus(run.status) in (
                    WorkflowRunStatus.COMPLETED,
                    WorkflowRunStatus.FAILED,
                    WorkflowRunStatus.CANCELLED,
                )
            emitted = False
            for event in events:
                payload = json.dumps({
                    "id": event.id,
                    "workflow_run_id": event.workflow_run_id,
                    "node_run_id": event.node_run_id,
                    "event_type": event.event_type,
                    "message": event.message,
                    "payload": event.payload_json,
                    "created_at": event.created_at.isoformat() if event.created_at else None,
                })
                yield f"id: {event.id}\nevent: {event.event_type}\ndata: {payload}\n\n"
                last_id = event.id
                emitted = True
            if not emitted:
                if run_terminal:
                    # All events emitted; the durable Trace is complete.
                    return
                # Heartbeat keeps proxies / clients from assuming the stream dropped.
                await asyncio.sleep(1)
                yield ": keep-alive\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")


def _parse_last_event_id(value: str | None) -> int:
    if value is None:
        return 0
    try:
        return max(int(value), 0)
    except ValueError:
        return 0
