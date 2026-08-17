"""Add workspaces table (isolated working directories bound to a Runner)."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_workspaces"
down_revision: Union[str, None] = "0010_runners"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("runner_id", sa.String(length=36), nullable=True),
        sa.Column("repository", sa.String(length=2048), nullable=False),
        sa.Column("path", sa.String(length=2048), nullable=True),
        sa.Column("branch", sa.String(length=255), nullable=True),
        sa.Column("base_branch", sa.String(length=255), nullable=True),
        sa.Column("workspace_type", sa.String(length=32), nullable=False, server_default=sa.text("'git_worktree'")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'creating'")),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=False),
        sa.Column("node_run_id", sa.String(length=36), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspaces_status", "workspaces", ["status"], unique=False)
    op.create_index("ix_workspaces_workflow_run_id", "workspaces", ["workflow_run_id"], unique=False)
    op.create_index("ix_workspaces_node_run_id", "workspaces", ["node_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_workspaces_node_run_id", table_name="workspaces")
    op.drop_index("ix_workspaces_workflow_run_id", table_name="workspaces")
    op.drop_index("ix_workspaces_status", table_name="workspaces")
    op.drop_table("workspaces")
