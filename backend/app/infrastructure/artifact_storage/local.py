"""Local filesystem ArtifactStorage.

Files are stored directly under a configured root, keyed by Artifact id.
Keys are validated so that `artifact://<id>` can never traverse outside the
root (Path Traversal protection).
"""

import re
from pathlib import Path
from typing import BinaryIO

from app.core.errors import RelayviaError
from app.infrastructure.artifact_storage.base import ArtifactStorage

_SAFE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


class LocalArtifactStorage(ArtifactStorage):
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, key: str) -> Path:
        if not isinstance(key, str) or not _SAFE_KEY.fullmatch(key):
            raise RelayviaError(
                "INVALID_ARTIFACT_KEY",
                "Artifact key is not a valid storage key",
                details={"key": key},
            )
        candidate = (self.root / key).resolve()
        if not candidate.is_relative_to(self.root):
            raise RelayviaError(
                "INVALID_ARTIFACT_KEY",
                "Artifact key escapes the storage root",
                details={"key": key},
            )
        return candidate

    def save_bytes(self, key: str, content: bytes) -> int:
        path = self._safe_path(key)
        path.write_bytes(content)
        return len(content)

    def open(self, key: str) -> BinaryIO:
        path = self._safe_path(key)
        if not path.exists():
            raise FileNotFoundError(key)
        return path.open("rb")

    def exists(self, key: str) -> bool:
        try:
            return self._safe_path(key).exists()
        except RelayviaError:
            return False

    def local_path(self, key: str) -> Path:
        path = self._safe_path(key)
        if not path.exists():
            raise FileNotFoundError(key)
        return path
