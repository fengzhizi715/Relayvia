from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.credentials.model import CredentialType


class CredentialCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: CredentialType
    value: str | None = Field(default=None, min_length=1)
    username: str | None = Field(default=None, min_length=1)
    password: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_secret(self) -> "CredentialCreate":
        if self.type in {CredentialType.API_KEY, CredentialType.BEARER_TOKEN} and not self.value:
            raise ValueError("value is required for api_key and bearer_token credentials")
        if self.type is CredentialType.BASIC_AUTH and (not self.username or not self.password):
            raise ValueError("username and password are required for basic_auth credentials")
        return self

    def secret_payload(self) -> dict[str, Any]:
        if self.type is CredentialType.BASIC_AUTH:
            return {"username": self.username, "password": self.password}
        return {"value": self.value}


class CredentialUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    value: str | None = Field(default=None, min_length=1)
    username: str | None = Field(default=None, min_length=1)
    password: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_secret_pair(self) -> "CredentialUpdate":
        if (self.username is None) != (self.password is None):
            raise ValueError("username and password must be provided together")
        return self


class CredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: CredentialType
    has_secret: bool = True
    created_at: datetime
    updated_at: datetime

