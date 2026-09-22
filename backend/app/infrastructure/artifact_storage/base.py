"""ArtifactStorage abstraction.

The database stores Artifact metadata; the physical content lives in a
Storage implementation. The Runtime / Connectors only talk to this interface,
never to concrete paths, so S3 / MinIO / OSS can be swapped in later.
"""

from abc import ABC, abstractmethod
from typing import BinaryIO


class ArtifactStorage(ABC):
    @abstractmethod
    def save_bytes(self, key: str, content: bytes) -> int:
        """Persist bytes under `key` and return the byte size."""

    @abstractmethod
    def save_stream(self, key: str, stream: BinaryIO) -> int:
        """Persist a seekable stream without requiring a JSON/base64 copy."""

    @abstractmethod
    def open(self, key: str) -> BinaryIO:
        """Open stored content for streaming download.

        Consumers must use this portable stream contract rather than assuming
        a local filesystem path, so API and Worker may run on different hosts.
        """

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Whether content exists for `key` (external URIs return False)."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete stored content if present. Must be idempotent."""
