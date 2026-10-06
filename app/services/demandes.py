"""Demandes d'actes : création (montant calculé ici, jamais fourni) et accès restreint au propriétaire."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..erreurs import ErreurMetier
from ..models import Demande
from ..schemas import DemandeCreation
from ..tarifs import calculer_montant


def creer(db: Session, usager_id: int, data: DemandeCreation) -> Demande:
    demande = Demande(
        usager_id=usager_id,
        type_acte=data.type_acte.value,
        nombre_copies=data.nombre_copies,
        montant=calculer_montant(data.type_acte, data.nombre_copies),
    )
    db.add(demande)
    db.commit()
    return demande


def lister(db: Session, usager_id: int) -> list[Demande]:
    return list(db.scalars(
        select(Demande).where(Demande.usager_id == usager_id).order_by(Demande.id.desc())
    ))


def demande_de_l_usager(db: Session, usager_id: int, demande_id: int) -> Demande:
    """404 aussi pour la demande d'un autre usager : on ne révèle pas son existence."""
    demande = db.scalar(
        select(Demande).where(Demande.id == demande_id, Demande.usager_id == usager_id)
    )
    if demande is None:
        raise ErreurMetier(404, "Demande introuvable")
    return demande
