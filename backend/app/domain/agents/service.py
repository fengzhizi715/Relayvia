from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.connectors.agents.http import HTTPAgentConnector
from app.connectors.http import HTTPConnectionConfig
from app.connectors.result import ConnectionTestResult, ConnectionTestStatus
from app.core.config import get_settings
from app.core.errors import RelayviaError
from app.domain.agents.model import Agent, AgentConnectorType, AgentStatus
from app.domain.agents.schemas import AgentCreate, AgentRead, AgentUpdate, Capability
from app.domain.credentials.service import get_credential_or_none
from app.domain.runners.models import Runner, runner_online
from app.domain.validation import validate_headers, validate_json_schema, validate_metadata
from app.domain.workflows.references import ensure_resource_not_referenced
from app.infrastructure.security.url_policy import validate_http_url


def _get_agent(db: Session, agent_id: str) -> Agent:
    agent = db.scalar(select(Agent).options(joinedload(Agent.credential)).where(Agent.id == agent_id))
    if agent is None:
        raise RelayviaError("AGENT_NOT_FOUND", "Agent not found", status_code=404)
    return agent


def _ensure_name_available(db: Session, name: str, current_id: str | None = None) -> None:
    query = select(Agent).where(func.lower(Agent.name) == name.lower())
    if current_id:
        query = query.where(Agent.id != current_id)
    if db.scalar(query) is not None:
        raise RelayviaError("DUPLICATE_NAME", "Agent name is already in use", details={"name": name})


def _validate_config(
    *,
    connector_type: AgentConnectorType,
    endpoint: str | None,
    health_check_url: str | None,
    headers: dict[str, str],
    runner_id: str | None,
    executable: str | None,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    if connector_type is AgentConnectorType.HTTP:
        if not endpoint:
            raise RelayviaError(
                "INVALID_AGENT_CONFIG",
                "endpoint is required for HTTP agents",
                details={"field": "endpoint"},
            )
        validate_http_url(endpoint, field="endpoint")
        if health_check_url:
            validate_http_url(health_check_url, field="health_check_url")
    elif health_check_url:
        raise RelayviaError(
            "INVALID_AGENT_CONFIG",
            "health_check_url is only supported for HTTP agents",
            details={"field": "health_check_url"},
        )
    if connector_type is AgentConnectorType.CODEX and not runner_id:
        raise RelayviaError(
            "INVALID_AGENT_CONFIG",
            "runner_id is required for Codex agents",
            details={"field": "runner_id"},
        )
    if executable is not None and (not executable.strip() or "\n" in executable or "\r" in executable):
        raise RelayviaError(
            "INVALID_AGENT_CONFIG",
            "executable must be a non-empty command path without line breaks",
            details={"field": "executable"},
        )
    validate_headers(headers)
    validate_json_schema(input_schema, field="input_schema")
    validate_json_schema(output_schema, field="output_schema")
    validate_metadata(metadata)


def to_read(agent: Agent) -> AgentRead:
    return AgentRead(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        connector_type=AgentConnectorType(agent.connector_type),
        endpoint=agent.endpoint,
        http_method=agent.http_method,
        health_check_url=agent.health_check_url,
        headers=agent.headers_json or {},
        runner_id=agent.runner_id,
        executable=agent.executable,
        capabilities=[Capability.model_validate(item) for item in (agent.capabilities_json or [])],
        input_schema=agent.input_schema_json or {},
        output_schema=agent.output_schema_json or {},
        credential_id=agent.credential_id,
        credential_name=agent.credential.name if agent.credential else None,
        timeout_seconds=agent.timeout_seconds,
        status=AgentStatus(agent.status),
        enabled=agent.enabled,
        metadata=agent.metadata_json or {},
        last_checked_at=agent.last_checked_at,
        last_latency_ms=agent.last_latency_ms,
        last_error=agent.last_error,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


def list_agents(
    db: Session,
    *,
    search: str | None = None,
    status: AgentStatus | None = None,
    enabled: bool | None = None,
) -> list[AgentRead]:
    query = select(Agent).options(joinedload(Agent.credential)).order_by(Agent.name)
    if search:
        query = query.where(Agent.name.ilike(f"%{search}%"))
    if status:
        query = query.where(Agent.status == status.value)
    if enabled is not None:
        query = query.where(Agent.enabled == enabled)
    return [to_read(agent) for agent in db.scalars(query).all()]


def create_agent(db: Session, payload: AgentCreate) -> AgentRead:
    _ensure_name_available(db, payload.name)
    _validate_config(
        connector_type=payload.connector_type,
        endpoint=payload.endpoint,
        health_check_url=payload.health_check_url,
        headers=payload.headers,
        runner_id=payload.runner_id,
        executable=payload.executable,
        input_schema=payload.input_schema,
        output_schema=payload.output_schema,
        metadata=payload.metadata,
    )
    credential = get_credential_or_none(db, payload.credential_id)
    if payload.runner_id and db.get(Runner, payload.runner_id) is None:
        raise RelayviaError("RUNNER_NOT_FOUND", "Runner not found", status_code=404)
    agent = Agent(
        name=payload.name,
        description=payload.description,
        connector_type=payload.connector_type.value,
        endpoint=payload.endpoint.rstrip("/") if payload.endpoint else None,
        http_method=payload.http_method.value,
        health_check_url=payload.health_check_url.rstrip("/") if payload.health_check_url else None,
        headers_json=payload.headers,
        runner_id=payload.runner_id,
        executable=payload.executable.strip() if payload.executable else None,
        capabilities_json=[capability.model_dump() for capability in payload.capabilities],
        input_schema_json=payload.input_schema,
        output_schema_json=payload.output_schema,
        credential=credential,
        timeout_seconds=payload.timeout_seconds,
        enabled=payload.enabled,
        metadata_json=payload.metadata,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return to_read(_get_agent(db, agent.id))


def update_agent(db: Session, agent_id: str, payload: AgentUpdate) -> AgentRead:
    agent = _get_agent(db, agent_id)
    changes = payload.model_dump(exclude_unset=True)
    if payload.name is not None:
        _ensure_name_available(db, payload.name, current_id=agent.id)
        agent.name = payload.name
    if "description" in changes:
        agent.description = payload.description
    if payload.connector_type is not None:
        agent.connector_type = payload.connector_type.value
        if payload.connector_type is not AgentConnectorType.HTTP:
            # HTTP invocation metadata must not leak into a local Runner
            # connector after changing connector type.
            agent.endpoint = None
            agent.health_check_url = None
            agent.headers_json = {}
    if "endpoint" in changes:
        agent.endpoint = payload.endpoint.rstrip("/") if payload.endpoint else None
    if payload.http_method is not None:
        agent.http_method = payload.http_method.value
    if "health_check_url" in changes:
        agent.health_check_url = payload.health_check_url.rstrip("/") if payload.health_check_url else None
    if payload.headers is not None:
        agent.headers_json = payload.headers
    if "runner_id" in changes:
        if payload.runner_id and db.get(Runner, payload.runner_id) is None:
            raise RelayviaError("RUNNER_NOT_FOUND", "Runner not found", status_code=404)
        agent.runner_id = payload.runner_id
    if "executable" in changes:
        agent.executable = payload.executable.strip() if payload.executable else None
    if payload.capabilities is not None:
        agent.capabilities_json = [capability.model_dump() for capability in payload.capabilities]
    if payload.input_schema is not None:
        agent.input_schema_json = payload.input_schema
    if payload.output_schema is not None:
        agent.output_schema_json = payload.output_schema
    if "credential_id" in changes:
        agent.credential = get_credential_or_none(db, payload.credential_id)
    if payload.timeout_seconds is not None:
        agent.timeout_seconds = payload.timeout_seconds
    if payload.enabled is not None:
        agent.enabled = payload.enabled
    if payload.metadata is not None:
        agent.metadata_json = payload.metadata

    _validate_config(
        connector_type=AgentConnectorType(agent.connector_type),
        endpoint=agent.endpoint,
        health_check_url=agent.health_check_url,
        headers=agent.headers_json or {},
        runner_id=agent.runner_id,
        executable=agent.executable,
        input_schema=agent.input_schema_json or {},
        output_schema=agent.output_schema_json or {},
        metadata=agent.metadata_json or {},
    )
    if any(field in changes for field in ("connector_type", "endpoint", "health_check_url", "credential_id", "runner_id", "executable")):
        agent.status = AgentStatus.UNKNOWN.value
        agent.last_error = None
    db.commit()
    db.refresh(agent)
    return to_read(_get_agent(db, agent.id))


def delete_agent(db: Session, agent_id: str) -> None:
    agent = _get_agent(db, agent_id)
    ensure_resource_not_referenced(db, "agent", agent.id)
    db.delete(agent)
    db.commit()


async def test_agent_connection(db: Session, agent_id: str) -> ConnectionTestResult:
    agent = _get_agent(db, agent_id)
    connector_type = AgentConnectorType(agent.connector_type)
    if connector_type is AgentConnectorType.CODEX:
        runner = db.get(Runner, agent.runner_id) if agent.runner_id else None
        available = bool(
            runner
            and runner_online(runner, offline_after_seconds=get_settings().runner_offline_seconds)
            and "codex" in set(runner.capabilities_json or [])
        )
        result = ConnectionTestResult(
            status=ConnectionTestStatus.HEALTHY if available else ConnectionTestStatus.UNHEALTHY,
            checked_at=datetime.now(timezone.utc),
            error_code=None if available else "RUNNER_CAPABILITY_UNAVAILABLE",
            message=(f"Runner {runner.name} is online with Codex capability" if available else "Assigned Runner is offline or lacks Codex capability"),
        )
    elif connector_type is not AgentConnectorType.HTTP:
        result = ConnectionTestResult(
            status=ConnectionTestStatus.UNSUPPORTED,
            checked_at=datetime.now(timezone.utc),
            error_code="CONNECTOR_NOT_IMPLEMENTED",
            message="Connection testing is only implemented for HTTP agents",
        )
    else:
        result = await HTTPAgentConnector().test_connection(
            HTTPConnectionConfig(
                url=agent.health_check_url,
                timeout_seconds=agent.timeout_seconds,
                headers=agent.headers_json or {},
                credential=agent.credential,
            )
        )
    if result.status is ConnectionTestStatus.HEALTHY:
        agent.status = AgentStatus.HEALTHY.value
        agent.last_error = None
    elif result.status is ConnectionTestStatus.UNHEALTHY:
        agent.status = AgentStatus.UNHEALTHY.value
        agent.last_error = result.message
    else:
        agent.status = AgentStatus.UNKNOWN.value
        agent.last_error = result.message
    agent.last_checked_at = result.checked_at
    agent.last_latency_ms = result.latency_ms
    db.commit()
    return result
