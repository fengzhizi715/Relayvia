"""Relayvia domain models and services.

Importing this package registers every persisted ORM model. SQLAlchemy resolves
string-based ``relationship()`` targets when mappers are configured, so every
database-touching entry point (API, Worker, tests) must load all models even if
it only references a subset.
"""

from app.domain.agents.model import Agent  # noqa: F401
from app.domain.artifacts.models import Artifact  # noqa: F401
from app.domain.credentials.model import Credential  # noqa: F401
from app.domain.execution.models import ExecutionTask  # noqa: F401
from app.domain.runs.events import RunEvent  # noqa: F401
from app.domain.runs.models import NodeRun, WorkflowRun  # noqa: F401
from app.domain.runners.models import Runner  # noqa: F401
from app.domain.services.model import Service, ServiceAction  # noqa: F401
from app.domain.workflows.model import Workflow, WorkflowVersion  # noqa: F401
from app.domain.workspaces.models import Workspace  # noqa: F401
