"""Secure Runner enrollment and enforce local execution references."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_runner_security_and_bindings"
down_revision: Union[str, None] = "0011_workspaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable supports a safe transition for pre-token Runner rows. They
    # cannot authenticate after upgrade and must enroll a new identity.
    op.add_column("runners", sa.Column("auth_token_hash", sa.String(length=64), nullable=True))
    op.add_column("agents", sa.Column("executable", sa.String(length=2048), nullable=True))
    op.create_index("ix_agents_runner_id", "agents", ["runner_id"], unique=False)
    op.create_index("ix_workspaces_runner_id", "workspaces", ["runner_id"], unique=False)
    op.create_unique_constraint("uq_workspaces_node_run", "workspaces", ["node_run_id"])

    # Earlier revisions accepted runner IDs without database constraints. Clear
    # only legacy orphan references before adding the restrictive foreign keys.
    op.execute(
        "UPDATE agents "
        "LEFT JOIN runners ON agents.runner_id = runners.id "
        "SET agents.runner_id = NULL "
        "WHERE agents.runner_id IS NOT NULL AND runners.id IS NULL"
    )
    op.execute(
        "UPDATE execution_tasks "
        "LEFT JOIN runners ON execution_tasks.runner_id = runners.id "
        "SET execution_tasks.runner_id = NULL "
        "WHERE execution_tasks.runner_id IS NOT NULL AND runners.id IS NULL"
    )
    op.execute(
        "UPDATE workspaces "
        "LEFT JOIN runners ON workspaces.runner_id = runners.id "
        "SET workspaces.runner_id = NULL "
        "WHERE workspaces.runner_id IS NOT NULL AND runners.id IS NULL"
    )

    op.create_foreign_key("fk_agents_runner_id", "agents", "runners", ["runner_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_execution_tasks_runner_id", "execution_tasks", "runners", ["runner_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_workspaces_runner_id", "workspaces", "runners", ["runner_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_workspaces_workflow_run_id", "workspaces", "workflow_runs", ["workflow_run_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_workspaces_node_run_id", "workspaces", "node_runs", ["node_run_id"], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    op.drop_constraint("fk_workspaces_node_run_id", "workspaces", type_="foreignkey")
    op.drop_constraint("fk_workspaces_workflow_run_id", "workspaces", type_="foreignkey")
    op.drop_constraint("fk_workspaces_runner_id", "workspaces", type_="foreignkey")
    op.drop_constraint("fk_execution_tasks_runner_id", "execution_tasks", type_="foreignkey")
    op.drop_constraint("fk_agents_runner_id", "agents", type_="foreignkey")
    op.drop_constraint("uq_workspaces_node_run", "workspaces", type_="unique")
    op.drop_index("ix_workspaces_runner_id", table_name="workspaces")
    op.drop_index("ix_agents_runner_id", table_name="agents")
    op.drop_column("agents", "executable")
    op.drop_column("runners", "auth_token_hash")
