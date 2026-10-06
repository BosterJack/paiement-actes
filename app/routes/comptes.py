from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as SessionDB

from ..database import get_db
from ..models import Usager
from ..schemas import Connexion, Session, UsagerCreation, UsagerLu
from ..securite import usager_courant
from ..services import comptes

router = APIRouter(prefix="/api", tags=["comptes"])


@router.post("/usagers", response_model=Session, status_code=status.HTTP_201_CREATED)
def inscrire(data: UsagerCreation, db: SessionDB = Depends(get_db)):
    """Crée un compte (NPI et email uniques) et ouvre une session."""
    return comptes.inscrire(db, data)


@router.post("/sessions", response_model=Session)
def se_connecter(data: Connexion, db: SessionDB = Depends(get_db)):
    """Connexion par NPI ou email + mot de passe."""
    return comptes.authentifier(db, data.identifiant, data.mot_de_passe)


@router.get("/usagers/moi", response_model=UsagerLu)
def moi(usager: Usager = Depends(usager_courant)):
    return usager
