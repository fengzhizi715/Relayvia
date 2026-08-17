from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Relayvia API"
    environment: str = "development"
    database_url: str = "mysql+pymysql://relayvia:relayvia@127.0.0.1:3306/relayvia"
    cors_origins: str = "http://localhost:5173"
    credential_encryption_key: str | None = None

    worker_id: str | None = None
    worker_poll_interval: float = 0.5
    worker_lease_seconds: int = 60
    worker_lease_renew_interval: float = 20.0
    worker_recovery_interval: float = 30.0

    artifact_storage_dir: str = "data/artifacts"
    artifact_max_bytes: int = 100 * 1024 * 1024

    runner_offline_seconds: int = 60
    backend_url: str = "http://127.0.0.1:8000"
    runner_root: str = ""
    runner_id_file: str = ""

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
