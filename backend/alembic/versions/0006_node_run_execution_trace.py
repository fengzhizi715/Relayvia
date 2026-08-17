"""Persist non-secret connector diagnostics on node runs."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_node_run_execution_trace"
down_revision: Union[str, None] = "0005_execution_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable columns first so existing NodeRun rows can be backfilled on
    # both MySQL 8 and SQLite-based development/test databases.
    if op.get_bind().dialect.name == "sqlite":
        # SQLite cannot ALTER a column to SET NOT NULL. Batch mode recreates
        # the table safely while preserving data and constraints.
        with op.batch_alter_table("node_runs") as batch_op:
            batch_op.add_column(sa.Column("execution_metadata_json", sa.JSON(), nullable=True))
            batch_op.add_column(sa.Column("artifact_refs_json", sa.JSON(), nullable=True))
        op.execute("UPDATE node_runs SET execution_metadata_json = '{}', artifact_refs_json = '[]'")
        with op.batch_alter_table("node_runs") as batch_op:
            batch_op.alter_column("execution_metadata_json", nullable=False, existing_type=sa.JSON())
            batch_op.alter_column("artifact_refs_json", nullable=False, existing_type=sa.JSON())
        return

    op.add_column("node_runs", sa.Column("execution_metadata_json", sa.JSON(), nullable=True))
    op.add_column("node_runs", sa.Column("artifact_refs_json", sa.JSON(), nullable=True))
    op.execute("UPDATE node_runs SET execution_metadata_json = '{}', artifact_refs_json = '[]'")
    op.alter_column("node_runs", "execution_metadata_json", nullable=False, existing_type=sa.JSON())
    op.alter_column("node_runs", "artifact_refs_json", nullable=False, existing_type=sa.JSON())


def downgrade() -> None:
    op.drop_column("node_runs", "artifact_refs_json")
    op.drop_column("node_runs", "execution_metadata_json")
