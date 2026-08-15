import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.errors import RelayviaError


class CredentialCrypto:
    """Encrypt credential payloads before they are persisted."""

    def __init__(self, key: str | None = None) -> None:
        encryption_key = key or get_settings().credential_encryption_key
        if not encryption_key:
            raise RelayviaError(
                "CREDENTIAL_ENCRYPTION_NOT_CONFIGURED",
                "Credential encryption is not configured",
                status_code=500,
            )
        try:
            self._fernet = Fernet(encryption_key.encode())
        except (ValueError, TypeError) as exc:
            raise RelayviaError(
                "CREDENTIAL_ENCRYPTION_INVALID",
                "Credential encryption configuration is invalid",
                status_code=500,
            ) from exc

    def encrypt(self, payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        return self._fernet.encrypt(serialized).decode()

    def decrypt(self, encrypted_payload: str) -> dict[str, Any]:
        try:
            value = self._fernet.decrypt(encrypted_payload.encode())
            payload = json.loads(value.decode())
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RelayviaError(
                "CREDENTIAL_DECRYPTION_FAILED",
                "Credential could not be decrypted",
                status_code=500,
            ) from exc
        if not isinstance(payload, dict):
            raise RelayviaError(
                "CREDENTIAL_DECRYPTION_FAILED",
                "Credential payload is invalid",
                status_code=500,
            )
        return payload

