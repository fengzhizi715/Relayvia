from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.domain.credentials.schemas import CredentialCreate, CredentialRead, CredentialUpdate
from app.domain.credentials.service import (
    create_credential,
    delete_credential,
    list_credentials,
    update_credential,
)
from app.infrastructure.database.session import get_db

router = APIRouter(prefix="/credentials", tags=["credentials"])


@router.get("", response_model=list[CredentialRead])
def get_credentials(db: Session = Depends(get_db)) -> list[CredentialRead]:
    return list_credentials(db)


@router.post("", response_model=CredentialRead, status_code=status.HTTP_201_CREATED)
def post_credential(payload: CredentialCreate, db: Session = Depends(get_db)) -> CredentialRead:
    return create_credential(db, payload)


@router.put("/{credential_id}", response_model=CredentialRead)
def put_credential(
    credential_id: str,
    payload: CredentialUpdate,
    db: Session = Depends(get_db),
) -> CredentialRead:
    return update_credential(db, credential_id, payload)


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_credential(credential_id: str, db: Session = Depends(get_db)) -> Response:
    delete_credential(db, credential_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

