from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Relayvia API"
    environment: str = "development"
    database_url: str = "mysql+pymysql://relayvia:relayvia@127.0.0.1:3306/relayvia"
    cors_origins: str = "http://localhost:5173"
    credential_encryption_key: str | None = None
    control_plane_token: str | None = None
    runner_enrollment_token: str | None = None
    # Private / loopback targets are useful for local and edge development,
    # but must be an explicit opt-in. Production defaults to public HTTP(S)
    # endpoints only.
    allow_private_network_urls: bool = False

    worker_id: str | None = None
    worker_poll_interval: float = 0.5
    # Bounded concurrency keeps one Worker process useful for independent
    # HTTP/logic nodes without changing queue ownership semantics.
    worker_concurrency: int = 4
    worker_lease_seconds: int = 60
    worker_lease_renew_interval: float = 20.0
    worker_recovery_interval: float = 30.0

    artifact_storage_dir: str = "data/artifacts"
    artifact_max_bytes: int = 100 * 1024 * 1024
    # Local storage is appropriate only when API and Worker share one durable
    # filesystem. Use the S3-compatible backend for multi-host deployments.
    artifact_storage_backend: str = "local"
    artifact_s3_bucket: str | None = None
    artifact_s3_prefix: str = "relayvia/artifacts"
    artifact_s3_region: str | None = None
    artifact_s3_endpoint_url: str | None = None

    runner_offline_seconds: int = 60
    # A Runner may execute independent tasks concurrently. Workspace-backed
    # coding tasks should use `worktree` isolation before raising this value.
    runner_concurrency: int = 2
    backend_url: str = "http://127.0.0.1:8000"
    runner_root: str = ""
    runner_id_file: str = ""
    # Command execution is disabled unless the Runner is wrapped by an
    # operator-provided sandbox, or trusted local development explicitly opts
    # into unsandboxed execution.
    runner_sandbox_command: str | None = None
    runner_allow_unsandboxed_execution: bool = False

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_prefix="RELAYVIA_",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
