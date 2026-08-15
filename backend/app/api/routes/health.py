import logging

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.infrastructure.database.session import get_engine

logger = logging.getLogger(__name__)
router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    database: str


def check_database() -> bool:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as exc:
        logger.warning("Database health check failed: %s", exc.__class__.__name__)
        return False


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    database_ok = check_database()
    return HealthResponse(
        status="ok" if database_ok else "degraded",
        service="relayvia-api",
        database="connected" if database_ok else "unavailable",
    )

