from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import paiements

router = APIRouter(prefix="/api/operateur", tags=["opérateur"])


async def corps_brut(request: Request) -> bytes:
    # La signature porte sur les octets reçus, pas sur un JSON re-sérialisé.
    return await request.body()


@router.post(
    "/notifications",
    responses={
        401: {"description": "Signature absente ou invalide : notification ignorée"},
        404: {"description": "Référence de paiement inconnue"},
        422: {"description": "Notification mal formée ou incohérente (montant, transaction)"},
    },
)
def recevoir_notification(
    corps: bytes = Depends(corps_brut),
    x_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Résultat signé de l'opérateur. 200 aussi pour un renvoi, pour qu'il cesse de réessayer."""
    paiement = paiements.traiter_notification(db, corps, x_signature)
    return {"reference": paiement.reference, "statut": paiement.statut}
