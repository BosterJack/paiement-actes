"""Identification simplifiée : chaque usager reçoit un jeton opaque à l'inscription."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Usager

bearer = HTTPBearer(auto_error=False)


def usager_courant(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Usager:
    usager = None
    if credentials is not None:
        usager = db.scalar(select(Usager).where(Usager.jeton == credentials.credentials))
    if usager is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton absent ou invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return usager
