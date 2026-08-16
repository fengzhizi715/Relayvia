"""ArtifactStorage abstraction.

The database stores Artifact metadata; the physical content lives in a
Storage implementation. The Runtime / Connectors only talk to this interface,
never to concrete paths, so S3 / MinIO / OSS can be swapped in later.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO


class ArtifactStorage(ABC):
    @abstractmethod
    def save_bytes(self, key: str, content: bytes) -> int:
        """Persist bytes under `key` and return the byte size."""

    @abstractmethod
    def open(self, key: str) -> BinaryIO:
        """Open the stored content for reading; raise FileNotFoundError when
        the key has no content."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Whether content exists for `key` (external URIs return False)."""

    @abstractmethod
    def local_path(self, key: str) -> Path:
        """The local filesystem path for `key` (only meaningful for local
        storage; used by streaming download)."""
