from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes.agents import router as agents_router
from app.api.routes.artifacts import router as artifacts_router
from app.api.routes.credentials import router as credentials_router
from app.api.routes.health import router as health_router
from app.api.routes.runs import node_runs_router, router as runs_router
from app.api.routes.runs import runs_under_workflow
from app.api.routes.runners import router as runners_router
from app.api.routes.trace import router as trace_router
from app.api.routes.workspaces import router as workspaces_router
from app.api.routes.services import router as services_router
from app.api.routes.workflows import router as workflows_router
from app.core.config import get_settings
from app.core.errors import RelayviaError


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(agents_router, prefix="/api")
    app.include_router(services_router, prefix="/api")
    app.include_router(credentials_router, prefix="/api")
    app.include_router(workflows_router, prefix="/api")
    app.include_router(runs_router, prefix="/api")
    app.include_router(runs_under_workflow, prefix="/api")
    app.include_router(node_runs_router, prefix="/api")
    app.include_router(artifacts_router, prefix="/api")
    app.include_router(trace_router, prefix="/api")
    app.include_router(runners_router, prefix="/api")
    app.include_router(workspaces_router, prefix="/api")

    @app.exception_handler(RelayviaError)
    async def relayvia_error_handler(_: Request, exc: RelayviaError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": jsonable_encoder(exc.errors())},
                }
            },
        )

    return app


app = create_app()
