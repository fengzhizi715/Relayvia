from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import RelayviaError
from app.domain.agents.model import Agent
from app.domain.credentials.model import Credential, CredentialType
from app.domain.credentials.schemas import CredentialCreate, CredentialRead, CredentialUpdate
from app.domain.services.model import Service
from app.infrastructure.security.crypto import CredentialCrypto


def _get_credential(db: Session, credential_id: str) -> Credential:
    credential = db.get(Credential, credential_id)
    if credential is None:
        raise RelayviaError("CREDENTIAL_NOT_FOUND", "Credential not found", status_code=404)
    return credential


def _ensure_name_available(db: Session, name: str, current_id: str | None = None) -> None:
    query = select(Credential).where(func.lower(Credential.name) == name.lower())
    if current_id:
        query = query.where(Credential.id != current_id)
    if db.scalar(query) is not None:
        raise RelayviaError("DUPLICATE_NAME", "Credential name is already in use", details={"name": name})


def to_read(credential: Credential) -> CredentialRead:
    return CredentialRead(
        id=credential.id,
        name=credential.name,
        type=CredentialType(credential.type),
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


def list_credentials(db: Session) -> list[CredentialRead]:
    credentials = db.scalars(select(Credential).order_by(Credential.name)).all()
    return [to_read(credential) for credential in credentials]


def create_credential(db: Session, payload: CredentialCreate) -> CredentialRead:
    _ensure_name_available(db, payload.name)
    credential = Credential(
        name=payload.name,
        type=payload.type.value,
        encrypted_payload=CredentialCrypto().encrypt(payload.secret_payload()),
    )
    db.add(credential)
    db.commit()
    db.refresh(credential)
    return to_read(credential)


def update_credential(db: Session, credential_id: str, payload: CredentialUpdate) -> CredentialRead:
    credential = _get_credential(db, credential_id)
    changes = payload.model_dump(exclude_unset=True)
    if payload.name is not None:
        _ensure_name_available(db, payload.name, current_id=credential.id)
        credential.name = payload.name

    if payload.value is not None or payload.username is not None or payload.password is not None:
        credential_type = CredentialType(credential.type)
        if credential_type is CredentialType.BASIC_AUTH:
            if payload.username is None or payload.password is None:
                raise RelayviaError(
                    "INVALID_CREDENTIAL",
                    "username and password are required together for basic_auth",
                )
            secret_payload = {"username": payload.username, "password": payload.password}
        else:
            if payload.value is None or payload.username is not None or payload.password is not None:
                raise RelayviaError(
                    "INVALID_CREDENTIAL",
                    "value is required for this credential type",
                )
            secret_payload = {"value": payload.value}
        credential.encrypted_payload = CredentialCrypto().encrypt(secret_payload)
    elif "value" in changes or "username" in changes or "password" in changes:
        raise RelayviaError("INVALID_CREDENTIAL", "A complete replacement secret is required")

    db.commit()
    db.refresh(credential)
    return to_read(credential)


def delete_credential(db: Session, credential_id: str) -> None:
    credential = _get_credential(db, credential_id)
    in_use = db.scalar(select(Agent.id).where(Agent.credential_id == credential_id).limit(1))
    if in_use is None:
        in_use = db.scalar(select(Service.id).where(Service.credential_id == credential_id).limit(1))
    if in_use is not None:
        raise RelayviaError(
            "CREDENTIAL_IN_USE",
            "Credential is referenced by an Agent or Service",
            status_code=409,
        )
    db.delete(credential)
    db.commit()


def get_credential_or_none(db: Session, credential_id: str | None) -> Credential | None:
    if credential_id is None:
        return None
    return _get_credential(db, credential_id)

