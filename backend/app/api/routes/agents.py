from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.connectors.result import ConnectionTestResult
from app.core.errors import RelayviaError
from app.domain.agents.model import AgentStatus
from app.domain.agents.schemas import AgentCreate, AgentRead, AgentUpdate
from app.domain.agents.service import (
    create_agent,
    delete_agent,
    list_agents,
    test_agent_connection,
    update_agent,
)
from app.infrastructure.database.session import get_db

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentRead])
def get_agents(
    search: str | None = Query(default=None),
    status_filter: AgentStatus | None = Query(default=None, alias="status"),
    enabled: bool | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[AgentRead]:
    return list_agents(db, search=search, status=status_filter, enabled=enabled)


@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
def post_agent(payload: AgentCreate, db: Session = Depends(get_db)) -> AgentRead:
    return create_agent(db, payload)


@router.get("/{agent_id}", response_model=AgentRead)
def get_agent(agent_id: str, db: Session = Depends(get_db)) -> AgentRead:
    for agent in list_agents(db):
        if agent.id == agent_id:
            return agent
    raise RelayviaError("AGENT_NOT_FOUND", "Agent not found", status_code=404)


@router.put("/{agent_id}", response_model=AgentRead)
def put_agent(agent_id: str, payload: AgentUpdate, db: Session = Depends(get_db)) -> AgentRead:
    return update_agent(db, agent_id, payload)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_agent(agent_id: str, db: Session = Depends(get_db)) -> Response:
    delete_agent(db, agent_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{agent_id}/test", response_model=ConnectionTestResult)
async def test_agent(agent_id: str, db: Session = Depends(get_db)) -> ConnectionTestResult:
    return await test_agent_connection(db, agent_id)
