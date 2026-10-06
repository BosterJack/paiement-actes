import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Demande, Usager
from .schemas import DemandeCreation, DemandeLue, TypeActeLu, UsagerCreation, UsagerCree
from .securite import usager_courant
from .tarifs import LIBELLES, TARIFS_UNITAIRES, calculer_montant

router = APIRouter(prefix="/api")


@router.post("/usagers", response_model=UsagerCree, status_code=status.HTTP_201_CREATED, tags=["usagers"])
def inscrire(data: UsagerCreation, db: Session = Depends(get_db)):
    usager = Usager(nom=data.nom, jeton=secrets.token_urlsafe(32))
    db.add(usager)
    db.commit()
    return usager


@router.get("/types-actes", response_model=list[TypeActeLu], tags=["demandes"])
def lister_types_actes():
    return [
        TypeActeLu(code=code, libelle=LIBELLES[code], tarif_unitaire=tarif)
        for code, tarif in TARIFS_UNITAIRES.items()
    ]


def demande_de_l_usager(db: Session, usager_id: int, demande_id: int) -> Demande:
    """404 aussi pour la demande d'un autre usager : on ne révèle pas son existence."""
    demande = db.scalar(
        select(Demande).where(Demande.id == demande_id, Demande.usager_id == usager_id)
    )
    if demande is None:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    return demande


@router.post("/demandes", response_model=DemandeLue, status_code=status.HTTP_201_CREATED, tags=["demandes"])
def creer_demande(
    data: DemandeCreation,
    db: Session = Depends(get_db),
    usager: Usager = Depends(usager_courant),
):
    demande = Demande(
        usager_id=usager.id,
        type_acte=data.type_acte.value,
        nombre_copies=data.nombre_copies,
        montant=calculer_montant(data.type_acte, data.nombre_copies),
    )
    db.add(demande)
    db.commit()
    return demande


@router.get("/demandes", response_model=list[DemandeLue], tags=["demandes"])
def lister_demandes(db: Session = Depends(get_db), usager: Usager = Depends(usager_courant)):
    return db.scalars(
        select(Demande).where(Demande.usager_id == usager.id).order_by(Demande.id.desc())
    ).all()


@router.get("/demandes/{demande_id}", response_model=DemandeLue, tags=["demandes"])
def lire_demande(
    demande_id: int, db: Session = Depends(get_db), usager: Usager = Depends(usager_courant)
):
    return demande_de_l_usager(db, usager.id, demande_id)
