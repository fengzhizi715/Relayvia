from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.connectors.result import ConnectionTestResult
from app.core.errors import RelayviaError
from app.domain.services.model import ServiceStatus
from app.domain.services.schemas import (
    ServiceActionCreate,
    ServiceActionRead,
    ServiceActionUpdate,
    ServiceCreate,
    ServiceRead,
    ServiceUpdate,
)
from app.domain.services.service import (
    create_action,
    create_service,
    delete_action,
    delete_service,
    list_actions,
    list_services,
    test_service_connection,
    update_action,
    update_service,
)
from app.infrastructure.database.session import get_db

router = APIRouter(prefix="/services", tags=["services"])


@router.get("", response_model=list[ServiceRead])
def get_services(
    search: str | None = Query(default=None),
    status_filter: ServiceStatus | None = Query(default=None, alias="status"),
    enabled: bool | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ServiceRead]:
    return list_services(db, search=search, status=status_filter, enabled=enabled)


@router.post("", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
def post_service(payload: ServiceCreate, db: Session = Depends(get_db)) -> ServiceRead:
    return create_service(db, payload)


@router.get("/{service_id}", response_model=ServiceRead)
def get_service(service_id: str, db: Session = Depends(get_db)) -> ServiceRead:
    services = list_services(db)
    for service in services:
        if service.id == service_id:
            return service
    raise RelayviaError("SERVICE_NOT_FOUND", "Service not found", status_code=404)


@router.put("/{service_id}", response_model=ServiceRead)
def put_service(service_id: str, payload: ServiceUpdate, db: Session = Depends(get_db)) -> ServiceRead:
    return update_service(db, service_id, payload)


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_service(service_id: str, db: Session = Depends(get_db)) -> Response:
    delete_service(db, service_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{service_id}/test", response_model=ConnectionTestResult)
async def test_service(service_id: str, db: Session = Depends(get_db)) -> ConnectionTestResult:
    return await test_service_connection(db, service_id)


@router.get("/{service_id}/actions", response_model=list[ServiceActionRead])
def get_actions(service_id: str, db: Session = Depends(get_db)) -> list[ServiceActionRead]:
    return list_actions(db, service_id)


@router.post("/{service_id}/actions", response_model=ServiceActionRead, status_code=status.HTTP_201_CREATED)
def post_action(
    service_id: str,
    payload: ServiceActionCreate,
    db: Session = Depends(get_db),
) -> ServiceActionRead:
    return create_action(db, service_id, payload)


@router.get("/{service_id}/actions/{action_id}", response_model=ServiceActionRead)
def get_action(service_id: str, action_id: str, db: Session = Depends(get_db)) -> ServiceActionRead:
    actions = list_actions(db, service_id)
    for action in actions:
        if action.id == action_id:
            return action
    raise RelayviaError("SERVICE_ACTION_NOT_FOUND", "Service action not found", status_code=404)


@router.put("/{service_id}/actions/{action_id}", response_model=ServiceActionRead)
def put_action(
    service_id: str,
    action_id: str,
    payload: ServiceActionUpdate,
    db: Session = Depends(get_db),
) -> ServiceActionRead:
    return update_action(db, service_id, action_id, payload)


@router.delete("/{service_id}/actions/{action_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_action(service_id: str, action_id: str, db: Session = Depends(get_db)) -> Response:
    delete_action(db, service_id, action_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
