from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Usager
from ..schemas import DemandeCreation, DemandeLue, TypeActeLu
from ..securite import usager_courant
from ..services import demandes
from ..tarifs import LIBELLES, TARIFS_UNITAIRES

router = APIRouter(prefix="/api", tags=["demandes"])


@router.get("/types-actes", response_model=list[TypeActeLu])
def lister_types_actes():
    return [
        TypeActeLu(code=code, libelle=LIBELLES[code], tarif_unitaire=tarif)
        for code, tarif in TARIFS_UNITAIRES.items()
    ]


@router.post("/demandes", response_model=DemandeLue, status_code=status.HTTP_201_CREATED)
def creer_demande(
    data: DemandeCreation, db: Session = Depends(get_db), usager: Usager = Depends(usager_courant)
):
    """Enregistre la demande et indique le montant à payer, calculé par le service."""
    return demandes.creer(db, usager.id, data)


@router.get("/demandes", response_model=list[DemandeLue])
def lister_demandes(db: Session = Depends(get_db), usager: Usager = Depends(usager_courant)):
    return demandes.lister(db, usager.id)


@router.get("/demandes/{demande_id}", response_model=DemandeLue)
def lire_demande(
    demande_id: int, db: Session = Depends(get_db), usager: Usager = Depends(usager_courant)
):
    return demandes.demande_de_l_usager(db, usager.id, demande_id)
