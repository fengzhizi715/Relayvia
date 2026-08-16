import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault(
    "RELAYVIA_CREDENTIAL_ENCRYPTION_KEY",
    "TnwmzeqQ-XffnsD3s2PF6VG4mBIeGltKpC_iuQCyg-M=",
)

from app.core.config import get_settings  # noqa: E402
from app.infrastructure.database.base import Base  # noqa: E402
from app.infrastructure.database.session import get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.domain.agents.model import Agent  # noqa: F401,E402
from app.domain.credentials.model import Credential  # noqa: F401,E402
from app.domain.runs.models import NodeRun, WorkflowRun  # noqa: F401,E402
from app.domain.services.model import Service, ServiceAction  # noqa: F401,E402
from app.domain.workflows.model import Workflow, WorkflowVersion  # noqa: F401,E402


@pytest.fixture(scope="session")
def http_test_server():
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status: int, body: bytes, content_type: str = "text/plain"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path in {"/health", "/api/health"}:
                self.respond(200, b'{"status":"ok"}', "application/json")
                return
            if self.path == "/fail":
                self.respond(503, b"unavailable")
                return
            self.respond(404, b"not found")

        def do_POST(self):  # noqa: N802
            self.respond(200, b'{"ok":true}', "application/json")

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join(timeout=2)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def client(db_session):
    get_settings.cache_clear()
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
