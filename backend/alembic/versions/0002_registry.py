"""Create Agent, Service, ServiceAction, and Credential registries."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_registry"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    ]


def upgrade() -> None:
    op.create_table(
        "credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_credentials_name"),
    )
    op.create_index("ix_credentials_name", "credentials", ["name"], unique=False)

    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("connector_type", sa.String(length=32), nullable=False, server_default=sa.text("'http'")),
        sa.Column("endpoint", sa.String(length=2048), nullable=True),
        sa.Column("http_method", sa.String(length=10), nullable=False, server_default=sa.text("'POST'")),
        sa.Column("health_check_url", sa.String(length=2048), nullable=True),
        sa.Column("headers_json", sa.JSON(), nullable=False),
        sa.Column("runner_id", sa.String(length=36), nullable=True),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("input_schema_json", sa.JSON(), nullable=False),
        sa.Column("output_schema_json", sa.JSON(), nullable=False),
        sa.Column("credential_id", sa.String(length=36), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_latency_ms", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["credential_id"], ["credentials.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_agents_name"),
    )
    op.create_index("ix_agents_name", "agents", ["name"], unique=False)
    op.create_index("ix_agents_credential_id", "agents", ["credential_id"], unique=False)
    op.create_index("ix_agents_status", "agents", ["status"], unique=False)
    op.create_index("ix_agents_enabled", "agents", ["enabled"], unique=False)

    op.create_table(
        "services",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("service_type", sa.String(length=32), nullable=False, server_default=sa.text("'http'")),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("credential_id", sa.String(length=36), nullable=True),
        sa.Column("health_check_url", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_latency_ms", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["credential_id"], ["credentials.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_services_name"),
    )
    op.create_index("ix_services_name", "services", ["name"], unique=False)
    op.create_index("ix_services_credential_id", "services", ["credential_id"], unique=False)
    op.create_index("ix_services_status", "services", ["status"], unique=False)
    op.create_index("ix_services_enabled", "services", ["enabled"], unique=False)

    op.create_table(
        "service_actions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("service_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("method", sa.String(length=10), nullable=False, server_default=sa.text("'POST'")),
        sa.Column("path", sa.String(length=2048), nullable=False),
        sa.Column("headers_json", sa.JSON(), nullable=False),
        sa.Column("query_schema_json", sa.JSON(), nullable=False),
        sa.Column("path_schema_json", sa.JSON(), nullable=False),
        sa.Column("input_schema_json", sa.JSON(), nullable=False),
        sa.Column("output_schema_json", sa.JSON(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("retry_policy_json", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_id", "name", name="uq_service_actions_service_name"),
    )
    op.create_index("ix_service_actions_service_id", "service_actions", ["service_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_service_actions_service_id", table_name="service_actions")
    op.drop_table("service_actions")

    op.drop_index("ix_services_enabled", table_name="services")
    op.drop_index("ix_services_status", table_name="services")
    op.drop_index("ix_services_credential_id", table_name="services")
    op.drop_index("ix_services_name", table_name="services")
    op.drop_table("services")

    op.drop_index("ix_agents_enabled", table_name="agents")
    op.drop_index("ix_agents_status", table_name="agents")
    op.drop_index("ix_agents_credential_id", table_name="agents")
    op.drop_index("ix_agents_name", table_name="agents")
    op.drop_table("agents")

    op.drop_index("ix_credentials_name", table_name="credentials")
    op.drop_table("credentials")
