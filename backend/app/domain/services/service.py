from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.connectors.result import ConnectionTestResult, ConnectionTestStatus
from app.connectors.services.http import HTTPServiceConnector
from app.connectors.http import HTTPConnectionConfig
from app.core.errors import RelayviaError
from app.domain.credentials.service import get_credential_or_none
from app.domain.services.model import HTTPMethod, Service, ServiceAction, ServiceStatus, ServiceType
from app.domain.services.schemas import (
    RetryPolicy,
    ServiceActionCreate,
    ServiceActionRead,
    ServiceActionUpdate,
    ServiceCreate,
    ServiceRead,
    ServiceUpdate,
)
from app.domain.validation import validate_headers, validate_json_schema, validate_metadata
from app.domain.workflows.references import ensure_resource_not_referenced
from app.infrastructure.security.url_policy import normalize_action_path, validate_http_url


def _get_service(db: Session, service_id: str) -> Service:
    service = db.scalar(
        select(Service)
        .options(joinedload(Service.credential), selectinload(Service.actions))
        .where(Service.id == service_id)
    )
    if service is None:
        raise RelayviaError("SERVICE_NOT_FOUND", "Service not found", status_code=404)
    return service


def _get_action(db: Session, service_id: str, action_id: str) -> ServiceAction:
    action = db.scalar(
        select(ServiceAction)
        .where(ServiceAction.id == action_id, ServiceAction.service_id == service_id)
    )
    if action is None:
        raise RelayviaError("SERVICE_ACTION_NOT_FOUND", "Service action not found", status_code=404)
    return action


def _ensure_service_name_available(db: Session, name: str, current_id: str | None = None) -> None:
    query = select(Service).where(func.lower(Service.name) == name.lower())
    if current_id:
        query = query.where(Service.id != current_id)
    if db.scalar(query) is not None:
        raise RelayviaError("DUPLICATE_NAME", "Service name is already in use", details={"name": name})


def _ensure_action_name_available(db: Session, service_id: str, name: str, current_id: str | None = None) -> None:
    query = select(ServiceAction).where(
        ServiceAction.service_id == service_id,
        func.lower(ServiceAction.name) == name.lower(),
    )
    if current_id:
        query = query.where(ServiceAction.id != current_id)
    if db.scalar(query) is not None:
        raise RelayviaError(
            "DUPLICATE_NAME",
            "Service action name is already in use for this service",
            details={"name": name},
        )


def _validate_action_config(
    *,
    path: str,
    headers: dict[str, str],
    query_schema: dict[str, Any],
    path_schema: dict[str, Any],
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    metadata: dict[str, Any],
) -> str:
    normalized_path = normalize_action_path(path)
    validate_headers(headers)
    validate_json_schema(query_schema, field="query_schema")
    validate_json_schema(path_schema, field="path_schema")
    validate_json_schema(input_schema, field="input_schema")
    validate_json_schema(output_schema, field="output_schema")
    validate_metadata(metadata)
    return normalized_path


def to_action_read(action: ServiceAction) -> ServiceActionRead:
    return ServiceActionRead(
        id=action.id,
        service_id=action.service_id,
        name=action.name,
        description=action.description,
        method=HTTPMethod(action.method),
        path=action.path,
        headers=action.headers_json or {},
        query_schema=action.query_schema_json or {},
        path_schema=action.path_schema_json or {},
        input_schema=action.input_schema_json or {},
        output_schema=action.output_schema_json or {},
        timeout_seconds=action.timeout_seconds,
        retry_policy=RetryPolicy.model_validate(action.retry_policy_json or {}),
        enabled=action.enabled,
        metadata=action.metadata_json or {},
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


def to_read(service: Service) -> ServiceRead:
    return ServiceRead(
        id=service.id,
        name=service.name,
        description=service.description,
        service_type=ServiceType(service.service_type),
        base_url=service.base_url,
        credential_id=service.credential_id,
        credential_name=service.credential.name if service.credential else None,
        health_check_url=service.health_check_url,
        status=ServiceStatus(service.status),
        enabled=service.enabled,
        metadata=service.metadata_json or {},
        last_checked_at=service.last_checked_at,
        last_latency_ms=service.last_latency_ms,
        last_error=service.last_error,
        actions_count=len(service.actions),
        created_at=service.created_at,
        updated_at=service.updated_at,
    )


def list_services(
    db: Session,
    *,
    search: str | None = None,
    status: ServiceStatus | None = None,
    enabled: bool | None = None,
) -> list[ServiceRead]:
    query = (
        select(Service)
        .options(joinedload(Service.credential), selectinload(Service.actions))
        .order_by(Service.name)
    )
    if search:
        query = query.where(Service.name.ilike(f"%{search}%"))
    if status:
        query = query.where(Service.status == status.value)
    if enabled is not None:
        query = query.where(Service.enabled == enabled)
    return [to_read(service) for service in db.scalars(query).unique().all()]


def create_service(db: Session, payload: ServiceCreate) -> ServiceRead:
    _ensure_service_name_available(db, payload.name)
    if payload.service_type is not ServiceType.HTTP:
        raise RelayviaError("UNSUPPORTED_SERVICE_TYPE", "Only HTTP services are supported in Phase 2")
    base_url = validate_http_url(payload.base_url, field="base_url")
    health_check_url = validate_http_url(payload.health_check_url, field="health_check_url") if payload.health_check_url else None
    validate_metadata(payload.metadata)
    credential = get_credential_or_none(db, payload.credential_id)
    service = Service(
        name=payload.name,
        description=payload.description,
        service_type=payload.service_type.value,
        base_url=base_url,
        credential=credential,
        health_check_url=health_check_url,
        enabled=payload.enabled,
        metadata_json=payload.metadata,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return to_read(_get_service(db, service.id))


def update_service(db: Session, service_id: str, payload: ServiceUpdate) -> ServiceRead:
    service = _get_service(db, service_id)
    changes = payload.model_dump(exclude_unset=True)
    if payload.name is not None:
        _ensure_service_name_available(db, payload.name, current_id=service.id)
        service.name = payload.name
    if "description" in changes:
        service.description = payload.description
    if payload.service_type is not None:
        if payload.service_type is not ServiceType.HTTP:
            raise RelayviaError("UNSUPPORTED_SERVICE_TYPE", "Only HTTP services are supported in Phase 2")
        service.service_type = payload.service_type.value
    if "base_url" in changes:
        if payload.base_url is None:
            raise RelayviaError("INVALID_URL", "base_url cannot be null", details={"field": "base_url"})
        service.base_url = validate_http_url(payload.base_url, field="base_url")
    if "credential_id" in changes:
        service.credential = get_credential_or_none(db, payload.credential_id)
    if "health_check_url" in changes:
        service.health_check_url = (
            validate_http_url(payload.health_check_url, field="health_check_url")
            if payload.health_check_url
            else None
        )
    if payload.enabled is not None:
        service.enabled = payload.enabled
    if payload.metadata is not None:
        validate_metadata(payload.metadata)
        service.metadata_json = payload.metadata
    if any(field in changes for field in ("base_url", "health_check_url", "credential_id")):
        service.status = ServiceStatus.UNKNOWN.value
        service.last_error = None
    db.commit()
    db.refresh(service)
    return to_read(_get_service(db, service.id))


def delete_service(db: Session, service_id: str) -> None:
    service = _get_service(db, service_id)
    ensure_resource_not_referenced(db, "service", service.id)
    db.delete(service)
    db.commit()


def list_actions(db: Session, service_id: str) -> list[ServiceActionRead]:
    _get_service(db, service_id)
    actions = db.scalars(
        select(ServiceAction).where(ServiceAction.service_id == service_id).order_by(ServiceAction.name)
    ).all()
    return [to_action_read(action) for action in actions]


def create_action(db: Session, service_id: str, payload: ServiceActionCreate) -> ServiceActionRead:
    _get_service(db, service_id)
    _ensure_action_name_available(db, service_id, payload.name)
    normalized_path = _validate_action_config(
        path=payload.path,
        headers=payload.headers,
        query_schema=payload.query_schema,
        path_schema=payload.path_schema,
        input_schema=payload.input_schema,
        output_schema=payload.output_schema,
        metadata=payload.metadata,
    )
    action = ServiceAction(
        service_id=service_id,
        name=payload.name,
        description=payload.description,
        method=payload.method.value,
        path=normalized_path,
        headers_json=payload.headers,
        query_schema_json=payload.query_schema,
        path_schema_json=payload.path_schema,
        input_schema_json=payload.input_schema,
        output_schema_json=payload.output_schema,
        timeout_seconds=payload.timeout_seconds,
        retry_policy_json=payload.retry_policy.model_dump(),
        enabled=payload.enabled,
        metadata_json=payload.metadata,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return to_action_read(action)


def update_action(db: Session, service_id: str, action_id: str, payload: ServiceActionUpdate) -> ServiceActionRead:
    action = _get_action(db, service_id, action_id)
    changes = payload.model_dump(exclude_unset=True)
    if payload.name is not None:
        _ensure_action_name_available(db, service_id, payload.name, current_id=action.id)
        action.name = payload.name
    if "description" in changes:
        action.description = payload.description
    if payload.method is not None:
        action.method = payload.method.value
    if "path" in changes:
        if payload.path is None:
            raise RelayviaError("INVALID_PATH", "path cannot be null")
        action.path = normalize_action_path(payload.path)
    if payload.headers is not None:
        action.headers_json = payload.headers
    if payload.query_schema is not None:
        action.query_schema_json = payload.query_schema
    if payload.path_schema is not None:
        action.path_schema_json = payload.path_schema
    if payload.input_schema is not None:
        action.input_schema_json = payload.input_schema
    if payload.output_schema is not None:
        action.output_schema_json = payload.output_schema
    if payload.timeout_seconds is not None:
        action.timeout_seconds = payload.timeout_seconds
    if payload.retry_policy is not None:
        action.retry_policy_json = payload.retry_policy.model_dump()
    if payload.enabled is not None:
        action.enabled = payload.enabled
    if payload.metadata is not None:
        action.metadata_json = payload.metadata

    _validate_action_config(
        path=action.path,
        headers=action.headers_json or {},
        query_schema=action.query_schema_json or {},
        path_schema=action.path_schema_json or {},
        input_schema=action.input_schema_json or {},
        output_schema=action.output_schema_json or {},
        metadata=action.metadata_json or {},
    )
    db.commit()
    db.refresh(action)
    return to_action_read(action)


def delete_action(db: Session, service_id: str, action_id: str) -> None:
    action = _get_action(db, service_id, action_id)
    ensure_resource_not_referenced(db, "service_action", action.id)
    db.delete(action)
    db.commit()


async def test_service_connection(db: Session, service_id: str) -> ConnectionTestResult:
    service = _get_service(db, service_id)
    if ServiceType(service.service_type) is not ServiceType.HTTP:
        result = ConnectionTestResult(
            status=ConnectionTestStatus.UNSUPPORTED,
            checked_at=datetime.now(timezone.utc),
            error_code="CONNECTOR_NOT_IMPLEMENTED",
            message="Connection testing is only implemented for HTTP services",
        )
    else:
        result = await HTTPServiceConnector().test_connection(
            HTTPConnectionConfig(
                url=service.health_check_url,
                timeout_seconds=30,
                credential=service.credential,
            )
        )
    if result.status is ConnectionTestStatus.HEALTHY:
        service.status = ServiceStatus.HEALTHY.value
        service.last_error = None
    elif result.status is ConnectionTestStatus.UNHEALTHY:
        service.status = ServiceStatus.UNHEALTHY.value
        service.last_error = result.message
    else:
        service.status = ServiceStatus.UNKNOWN.value
        service.last_error = result.message
    service.last_checked_at = result.checked_at
    service.last_latency_ms = result.latency_ms
    db.commit()
    return result
