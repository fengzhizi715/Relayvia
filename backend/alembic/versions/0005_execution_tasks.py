"""Add execution_tasks (MySQL-backed Execution Queue)."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_execution_tasks"
down_revision: Union[str, None] = "0004_runtime_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "execution_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=False),
        sa.Column("node_run_id", sa.String(length=36), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False, server_default=sa.text("'node_execution'")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("locked_by", sa.String(length=120), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_key", sa.String(length=128), nullable=True),
        sa.Column("last_error_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["node_run_id"], ["node_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_run_id", name="uq_execution_tasks_node_run"),
    )
    op.create_index("ix_execution_tasks_workflow_run_id", "execution_tasks", ["workflow_run_id"], unique=False)
    op.create_index("ix_execution_tasks_node_run_id", "execution_tasks", ["node_run_id"], unique=False)
    op.create_index("ix_execution_tasks_status", "execution_tasks", ["status"], unique=False)
    op.create_index("ix_execution_tasks_available_at", "execution_tasks", ["available_at"], unique=False)
    op.create_index("ix_execution_tasks_claim", "execution_tasks", ["status", "available_at", "priority", "created_at"], unique=False)
    op.create_index("ix_execution_tasks_run", "execution_tasks", ["workflow_run_id", "status"], unique=False)
    op.create_index("ix_execution_tasks_lease_expires", "execution_tasks", ["lease_expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_execution_tasks_lease_expires", table_name="execution_tasks")
    op.drop_index("ix_execution_tasks_run", table_name="execution_tasks")
    op.drop_index("ix_execution_tasks_claim", table_name="execution_tasks")
    op.drop_index("ix_execution_tasks_available_at", table_name="execution_tasks")
    op.drop_index("ix_execution_tasks_status", table_name="execution_tasks")
    op.drop_index("ix_execution_tasks_node_run_id", table_name="execution_tasks")
    op.drop_index("ix_execution_tasks_workflow_run_id", table_name="execution_tasks")
    op.drop_table("execution_tasks")
