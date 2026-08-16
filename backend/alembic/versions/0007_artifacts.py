"""Add artifacts table (metadata only; content lives in ArtifactStorage)."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_artifacts"
down_revision: Union[str, None] = "0006_node_run_execution_trace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=False),
        sa.Column("producer_node_run_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False, server_default=sa.text("'file'")),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("uri", sa.String(length=2048), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["producer_node_run_id"], ["node_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uri", name="uq_artifacts_uri"),
    )
    op.create_index("ix_artifacts_workflow_run_id", "artifacts", ["workflow_run_id"], unique=False)
    op.create_index("ix_artifacts_producer_node_run_id", "artifacts", ["producer_node_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_artifacts_producer_node_run_id", table_name="artifacts")
    op.drop_index("ix_artifacts_workflow_run_id", table_name="artifacts")
    op.drop_table("artifacts")
