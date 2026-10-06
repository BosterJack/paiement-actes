from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import paiements
from .database import get_db
from .demandes import demande_de_l_usager
from .models import Paiement, Usager
from .operateur import ClientOperateur, get_operateur
from .schemas import PaiementCreation, PaiementLu
from .securite import usager_courant

router = APIRouter(prefix="/api", tags=["paiements"])


@router.post(
    "/demandes/{demande_id}/paiements",
    response_model=PaiementLu,
    status_code=status.HTTP_202_ACCEPTED,
    responses={200: {"description": "Renvoi d'une requête déjà reçue (même Idempotency-Key)"}},
)
def payer_demande(
    demande_id: int,
    data: PaiementCreation,
    response: Response,
    idempotency_key: str = Header(min_length=8, max_length=100),
    db: Session = Depends(get_db),
    usager: Usager = Depends(usager_courant),
    operateur_client: ClientOperateur = Depends(get_operateur),
):
    """Lance le paiement. 202 : débit demandé, résultat attendu de l'opérateur."""
    demande = demande_de_l_usager(db, usager.id, demande_id)
    paiement, cree = paiements.lancer_paiement(
        db, operateur_client, demande, idempotency_key, data.operateur.value, data.telephone
    )
    if not cree:
        response.status_code = status.HTTP_200_OK
    return paiement


@router.get("/demandes/{demande_id}/paiements", response_model=list[PaiementLu])
def lister_paiements_demande(
    demande_id: int, db: Session = Depends(get_db), usager: Usager = Depends(usager_courant)
):
    demande = demande_de_l_usager(db, usager.id, demande_id)
    paiements.expirer_paiements_echus(db, demande.id)
    return db.scalars(
        select(Paiement).where(Paiement.demande_id == demande.id).order_by(Paiement.id.desc())
    ).all()


async def corps_brut(request: Request) -> bytes:
    # La signature porte sur les octets reçus, pas sur un JSON re-sérialisé.
    return await request.body()


@router.post("/operateur/notifications", tags=["opérateur"])
def recevoir_notification(
    corps: bytes = Depends(corps_brut),
    x_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Appelé par l'opérateur. 200 aussi pour un renvoi, pour qu'il cesse de réessayer."""
    paiement = paiements.traiter_notification(db, corps, x_signature)
    return {"reference": paiement.reference, "statut": paiement.statut}


@router.get("/paiements/{paiement_id}", response_model=PaiementLu)
def lire_paiement(
    paiement_id: int, db: Session = Depends(get_db), usager: Usager = Depends(usager_courant)
):
    paiement = db.scalar(
        select(Paiement).where(Paiement.id == paiement_id, Paiement.usager_id == usager.id)
    )
    if paiement is None:
        raise HTTPException(status_code=404, detail="Paiement introuvable")
    if paiements.expirer_paiements_echus(db, paiement.demande_id):
        db.refresh(paiement)
    return paiement
