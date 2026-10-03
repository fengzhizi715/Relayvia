"""Normalize workspace types and add cleanup lifecycle constraints."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_workspace_lifecycle"
down_revision: Union[str, None] = "0012_runner_security"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE workspaces SET workspace_type = 'local' WHERE workspace_type = 'local_repository'")
    op.execute("UPDATE workspaces SET workspace_type = 'worktree' WHERE workspace_type = 'git_worktree'")
    op.alter_column("workspaces", "workspace_type", existing_type=sa.String(length=32), server_default=sa.text("'worktree'"), existing_nullable=False)
    op.create_check_constraint("ck_workspaces_type", "workspaces", "workspace_type IN ('local', 'worktree')")
    op.create_check_constraint(
        "ck_workspaces_status",
        "workspaces",
        "status IN ('creating', 'ready', 'in_use', 'failed', 'releasing', 'cleaning', 'cleanup_failed', 'released')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_workspaces_status", "workspaces", type_="check")
    op.drop_constraint("ck_workspaces_type", "workspaces", type_="check")
    op.execute("UPDATE workspaces SET workspace_type = 'local_repository' WHERE workspace_type = 'local'")
    op.execute("UPDATE workspaces SET workspace_type = 'git_worktree' WHERE workspace_type = 'worktree'")
    op.alter_column("workspaces", "workspace_type", existing_type=sa.String(length=32), server_default=sa.text("'git_worktree'"), existing_nullable=False)
