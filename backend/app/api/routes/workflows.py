from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.domain.workflows.schemas import (
    WorkflowCreate,
    WorkflowGraphRead,
    WorkflowGraphUpdate,
    WorkflowRead,
    WorkflowUpdate,
    WorkflowVersionCreate,
    WorkflowVersionRead,
)
from app.domain.workflows.service import (
    create_version,
    create_workflow,
    delete_workflow,
    get_draft_graph,
    get_version,
    get_workflow,
    list_versions,
    list_workflows,
    update_draft_graph,
    update_workflow,
)
from app.infrastructure.database.session import get_db


router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=list[WorkflowRead])
def get_workflows(
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[WorkflowRead]:
    return list_workflows(db, include_archived=include_archived)


@router.post("", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED)
def post_workflow(payload: WorkflowCreate, db: Session = Depends(get_db)) -> WorkflowRead:
    return create_workflow(db, payload)


@router.get("/{workflow_id}", response_model=WorkflowRead)
def get_workflow_detail(workflow_id: str, db: Session = Depends(get_db)) -> WorkflowRead:
    return get_workflow(db, workflow_id)


@router.put("/{workflow_id}", response_model=WorkflowRead)
def put_workflow(workflow_id: str, payload: WorkflowUpdate, db: Session = Depends(get_db)) -> WorkflowRead:
    return update_workflow(db, workflow_id, payload)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_workflow(workflow_id: str, db: Session = Depends(get_db)) -> Response:
    delete_workflow(db, workflow_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{workflow_id}/graph", response_model=WorkflowGraphRead)
def get_workflow_graph(workflow_id: str, db: Session = Depends(get_db)) -> WorkflowGraphRead:
    return get_draft_graph(db, workflow_id)


@router.put("/{workflow_id}/graph", response_model=WorkflowGraphRead)
def put_workflow_graph(
    workflow_id: str,
    payload: WorkflowGraphUpdate,
    db: Session = Depends(get_db),
) -> WorkflowGraphRead:
    return update_draft_graph(db, workflow_id, payload.graph)


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionRead])
def get_workflow_versions(workflow_id: str, db: Session = Depends(get_db)) -> list[WorkflowVersionRead]:
    return list_versions(db, workflow_id)


@router.post("/{workflow_id}/versions", response_model=WorkflowVersionRead, status_code=status.HTTP_201_CREATED)
def post_workflow_version(
    workflow_id: str,
    payload: WorkflowVersionCreate | None = None,
    db: Session = Depends(get_db),
) -> WorkflowVersionRead:
    return create_version(db, workflow_id, payload.change_note if payload else None)


@router.get("/{workflow_id}/versions/{version}", response_model=WorkflowVersionRead)
def get_workflow_version(workflow_id: str, version: int, db: Session = Depends(get_db)) -> WorkflowVersionRead:
    return get_version(db, workflow_id, version)

