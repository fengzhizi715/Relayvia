from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.domain.execution.schemas import ExecutionTaskRead
from app.domain.execution.service import list_execution_tasks
from app.domain.runs.schemas import NodeRunRead, WorkflowRunCreate, WorkflowRunRead, WorkflowRunSummary
from app.domain.runs.service import (
    approve_node_run,
    cancel_run,
    create_run,
    get_node_run,
    get_run,
    list_node_runs,
    list_runs,
    pause_run,
    reject_node_run,
    resume_run,
    start_run,
    submit_node_run,
)
from app.infrastructure.database.session import get_db
from app.runtime.state_machine import WorkflowRunStatus

router = APIRouter(prefix="/workflow-runs", tags=["runs"])


@router.get("", response_model=list[WorkflowRunSummary])
def get_runs(
    workflow_id: str | None = Query(default=None),
    run_status: WorkflowRunStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[WorkflowRunSummary]:
    return list_runs(db, workflow_id=workflow_id, status=run_status, limit=limit, offset=offset)


@router.get("/{run_id}", response_model=WorkflowRunRead)
def get_run_detail(run_id: str, db: Session = Depends(get_db)) -> WorkflowRunRead:
    return get_run(db, run_id)


@router.post("/{run_id}/start", response_model=WorkflowRunRead)
def post_start_run(run_id: str, db: Session = Depends(get_db)) -> WorkflowRunRead:
    return start_run(db, run_id)


@router.post("/{run_id}/pause", response_model=WorkflowRunRead)
def post_pause_run(run_id: str, db: Session = Depends(get_db)) -> WorkflowRunRead:
    return pause_run(db, run_id)


@router.post("/{run_id}/resume", response_model=WorkflowRunRead)
def post_resume_run(run_id: str, db: Session = Depends(get_db)) -> WorkflowRunRead:
    return resume_run(db, run_id)


@router.post("/{run_id}/cancel", response_model=WorkflowRunRead)
def post_cancel_run(run_id: str, db: Session = Depends(get_db)) -> WorkflowRunRead:
    return cancel_run(db, run_id)


@router.get("/{run_id}/nodes", response_model=list[NodeRunRead])
def get_run_nodes(run_id: str, db: Session = Depends(get_db)) -> list[NodeRunRead]:
    return list_node_runs(db, run_id)


@router.get("/{run_id}/nodes/{node_run_id}", response_model=NodeRunRead)
def get_run_node(run_id: str, node_run_id: str, db: Session = Depends(get_db)) -> NodeRunRead:
    return get_node_run(db, run_id, node_run_id)


@router.get("/{run_id}/execution-tasks", response_model=list[ExecutionTaskRead])
def get_run_execution_tasks(run_id: str, db: Session = Depends(get_db)) -> list[ExecutionTaskRead]:
    return list_execution_tasks(db, run_id)


node_runs_router = APIRouter(prefix="/node-runs", tags=["node-runs"])


class NodeRunSubmitRequest(BaseModel):
    input: dict[str, object] = Field(default_factory=dict)


@node_runs_router.post("/{node_run_id}/approve", response_model=NodeRunRead)
def post_approve_node_run(node_run_id: str, db: Session = Depends(get_db)) -> NodeRunRead:
    return approve_node_run(db, node_run_id)


@node_runs_router.post("/{node_run_id}/reject", response_model=NodeRunRead)
def post_reject_node_run(node_run_id: str, db: Session = Depends(get_db)) -> NodeRunRead:
    return reject_node_run(db, node_run_id)


@node_runs_router.post("/{node_run_id}/submit", response_model=NodeRunRead)
def post_submit_node_run(node_run_id: str, payload: NodeRunSubmitRequest, db: Session = Depends(get_db)) -> NodeRunRead:
    return submit_node_run(db, node_run_id, payload.input)


runs_under_workflow = APIRouter(prefix="/workflows", tags=["runs"])


@runs_under_workflow.post("/{workflow_id}/runs", response_model=WorkflowRunRead, status_code=status.HTTP_201_CREATED)
def post_workflow_run(workflow_id: str, payload: WorkflowRunCreate, db: Session = Depends(get_db)) -> WorkflowRunRead:
    return create_run(db, workflow_id, payload)
