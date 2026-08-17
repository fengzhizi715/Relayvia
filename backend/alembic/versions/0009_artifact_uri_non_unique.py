"""Allow repeated external Artifact URIs across Workflow Runs."""

from typing import Sequence, Union

from alembic import op


revision: str = "0009_artifact_uri_non_unique"
down_revision: Union[str, None] = "0008_run_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("artifacts") as batch_op:
            batch_op.drop_constraint("uq_artifacts_uri", type_="unique")
    else:
        op.drop_constraint("uq_artifacts_uri", "artifacts", type_="unique")
    op.create_index("ix_artifacts_uri", "artifacts", ["uri"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_artifacts_uri", table_name="artifacts")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("artifacts") as batch_op:
            batch_op.create_unique_constraint("uq_artifacts_uri", ["uri"])
    else:
        op.create_unique_constraint("uq_artifacts_uri", "artifacts", ["uri"])
