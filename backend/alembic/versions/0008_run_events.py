"""Add run_events table (durable Workflow Execution Trace)."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_run_events"
down_revision: Union[str, None] = "0007_artifacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=False),
        sa.Column("node_run_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_run_id"], ["node_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_events_workflow_run_id", "run_events", ["workflow_run_id"], unique=False)
    op.create_index("ix_run_events_node_run_id", "run_events", ["node_run_id"], unique=False)
    op.create_index("ix_run_events_run_id", "run_events", ["workflow_run_id", "id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_run_events_run_id", table_name="run_events")
    op.drop_index("ix_run_events_node_run_id", table_name="run_events")
    op.drop_index("ix_run_events_workflow_run_id", table_name="run_events")
    op.drop_table("run_events")
