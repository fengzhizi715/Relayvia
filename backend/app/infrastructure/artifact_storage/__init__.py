"""Artifact storage implementations."""

from functools import lru_cache

from app.core.config import get_settings
from app.infrastructure.artifact_storage.base import ArtifactStorage
from app.infrastructure.artifact_storage.local import LocalArtifactStorage


@lru_cache
def get_artifact_storage() -> ArtifactStorage:
    return LocalArtifactStorage(get_settings().artifact_storage_dir)


__all__ = ["ArtifactStorage", "LocalArtifactStorage", "get_artifact_storage"]
