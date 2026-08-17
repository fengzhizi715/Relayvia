"""Add runners table and runner-targeting columns on execution_tasks."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_runners"
down_revision: Union[str, None] = "0009_artifact_uri_non_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runners",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'offline'")),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runners_status", "runners", ["status"], unique=False)
    op.create_index("ix_runners_last_seen_at", "runners", ["last_seen_at"], unique=False)

    op.add_column("execution_tasks", sa.Column("runner_id", sa.String(length=36), nullable=True))
    op.add_column("execution_tasks", sa.Column("required_capability", sa.String(length=32), nullable=True))
    op.create_index("ix_execution_tasks_runner_id", "execution_tasks", ["runner_id"], unique=False)
    op.create_index("ix_execution_tasks_required_capability", "execution_tasks", ["required_capability"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_execution_tasks_required_capability", table_name="execution_tasks")
    op.drop_index("ix_execution_tasks_runner_id", table_name="execution_tasks")
    op.drop_column("execution_tasks", "required_capability")
    op.drop_column("execution_tasks", "runner_id")
    op.drop_index("ix_runners_last_seen_at", table_name="runners")
    op.drop_index("ix_runners_status", table_name="runners")
    op.drop_table("runners")
