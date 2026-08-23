"""Artifact storage implementations."""

from functools import lru_cache

from app.core.config import get_settings
from app.core.errors import RelayviaError
from app.infrastructure.artifact_storage.base import ArtifactStorage
from app.infrastructure.artifact_storage.local import LocalArtifactStorage
from app.infrastructure.artifact_storage.s3 import S3ArtifactStorage


@lru_cache
def get_artifact_storage() -> ArtifactStorage:
    settings = get_settings()
    if settings.artifact_storage_backend == "local":
        return LocalArtifactStorage(settings.artifact_storage_dir)
    if settings.artifact_storage_backend == "s3":
        if not settings.artifact_s3_bucket:
            raise RelayviaError("ARTIFACT_STORAGE_CONFIG_INVALID", "RELAYVIA_ARTIFACT_S3_BUCKET is required for S3 storage", status_code=500)
        return S3ArtifactStorage(
            bucket=settings.artifact_s3_bucket,
            prefix=settings.artifact_s3_prefix,
            region=settings.artifact_s3_region,
            endpoint_url=settings.artifact_s3_endpoint_url,
        )
    raise RelayviaError("ARTIFACT_STORAGE_CONFIG_INVALID", "Artifact storage backend must be 'local' or 's3'", status_code=500)


__all__ = ["ArtifactStorage", "LocalArtifactStorage", "S3ArtifactStorage", "get_artifact_storage"]
