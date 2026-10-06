from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Usager
from ..operateur import ClientOperateur, get_operateur
from ..schemas import PaiementCreation, PaiementLu
from ..securite import usager_courant
from ..services import paiements
from ..services.demandes import demande_de_l_usager

router = APIRouter(prefix="/api", tags=["paiements"])


@router.post(
    "/demandes/{demande_id}/paiements",
    response_model=PaiementLu,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        200: {"description": "Renvoi d'une requête déjà reçue (même Idempotency-Key) : aucun nouveau débit"},
        409: {"description": "Demande déjà payée ou paiement déjà en cours"},
        422: {"description": "Données invalides (téléphone, opérateur, clé réutilisée) : aucun débit"},
        502: {"description": "Opérateur injoignable : paiement ECHOUE, l'usager peut réessayer"},
    },
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
    """Lance le paiement. 202 : débit demandé, le résultat arrivera de l'opérateur."""
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
    """Historique des tentatives de paiement d'une demande (la plus récente d'abord)."""
    demande = demande_de_l_usager(db, usager.id, demande_id)
    return paiements.lister_pour_demande(db, demande.id)


@router.get("/paiements/{paiement_id}", response_model=PaiementLu)
def lire_paiement(
    paiement_id: int, db: Session = Depends(get_db), usager: Usager = Depends(usager_courant)
):
    """État d'un paiement : EN_COURS, REUSSI, ECHOUE ou EXPIRE."""
    return paiements.paiement_de_l_usager(db, usager.id, paiement_id)
