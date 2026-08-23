"""S3-compatible Artifact storage for multi-host Relayvia deployments."""

from __future__ import annotations

from typing import Any, BinaryIO

from botocore.exceptions import ClientError

from app.core.errors import RelayviaError
from app.infrastructure.artifact_storage.base import ArtifactStorage
from app.infrastructure.artifact_storage.local import _SAFE_KEY


class S3ArtifactStorage(ArtifactStorage):
    """Persist Artifact bytes to S3, MinIO, or another S3-compatible store.

    Authentication uses boto3's provider chain (workload identity,
    environment, or local profile), never a Relayvia Registry Credential.
    """

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "relayvia/artifacts",
        region: str | None = None,
        endpoint_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        if not bucket.strip():
            raise RelayviaError("ARTIFACT_STORAGE_CONFIG_INVALID", "S3 Artifact storage requires a bucket name", status_code=500)
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        if client is None:
            import boto3

            client = boto3.client("s3", region_name=region, endpoint_url=endpoint_url)
        self.client = client

    def _key(self, key: str) -> str:
        if not isinstance(key, str) or not _SAFE_KEY.fullmatch(key):
            raise RelayviaError("INVALID_ARTIFACT_KEY", "Artifact key is not a valid storage key", details={"key": key})
        return f"{self.prefix}/{key}" if self.prefix else key

    def save_bytes(self, key: str, content: bytes) -> int:
        self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=content)
        return len(content)

    def open(self, key: str) -> BinaryIO:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=self._key(key))["Body"]
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}:
                raise FileNotFoundError(key) from exc
            raise

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}:
                return False
            raise
