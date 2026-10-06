"""Logique métier des paiements (indépendante de HTTP)."""
import logging
import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import config
from .database import maintenant
from .models import Demande, Paiement, StatutDemande, StatutPaiement
from .operateur import ClientOperateur, OperateurIndisponible

log = logging.getLogger("paiements")


class ErreurMetier(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message


def paiement_par_cle(db: Session, usager_id: int, cle: str) -> Paiement | None:
    return db.scalar(
        select(Paiement).where(Paiement.usager_id == usager_id, Paiement.cle_idempotence == cle)
    )


def expirer_paiements_echus(db: Session, demande_id: int | None = None) -> int:
    """Passe en EXPIRE les paiements restés EN_COURS au-delà du délai.

    UPDATE conditionnel sur statut = EN_COURS : si le résultat de l'opérateur arrive
    au même moment, un seul des deux l'emporte.
    """
    limite = maintenant() - timedelta(seconds=config.PAIEMENT_EXPIRATION_SECONDES)
    stmt = (
        update(Paiement)
        .where(Paiement.statut == StatutPaiement.EN_COURS.value, Paiement.cree_le < limite)
        .values(
            statut=StatutPaiement.EXPIRE.value,
            motif="Aucun résultat de l'opérateur dans le délai imparti",
            maj_le=maintenant(),
        )
    )
    if demande_id is not None:
        stmt = stmt.where(Paiement.demande_id == demande_id)
    nombre = db.execute(stmt).rowcount
    db.commit()
    if nombre:
        log.warning("%s paiement(s) expiré(s) sans résultat de l'opérateur", nombre)
    return nombre


def lancer_paiement(
    db: Session,
    operateur_client: ClientOperateur,
    demande: Demande,
    cle_idempotence: str,
    operateur: str,
    telephone: str,
) -> tuple[Paiement, bool]:
    """Retourne (paiement, cree). cree=False si la requête est un renvoi de la même clé."""
    existant = paiement_par_cle(db, demande.usager_id, cle_idempotence)
    if existant is not None:
        return _rejouer(existant, demande), False

    expirer_paiements_echus(db, demande.id)
    db.refresh(demande)
    if demande.statut == StatutDemande.PAYEE.value:
        raise ErreurMetier(409, "Cette demande est déjà payée")

    paiement = Paiement(
        reference=uuid.uuid4().hex,
        demande_id=demande.id,
        usager_id=demande.usager_id,
        cle_idempotence=cle_idempotence,
        operateur=operateur,
        telephone=telephone,
        montant=demande.montant,  # toujours le montant calculé par le service
    )
    db.add(paiement)
    try:
        # Le paiement est enregistré AVANT d'appeler l'opérateur : c'est l'index unique
        # qui désigne l'unique gagnant en cas de requêtes simultanées.
        db.commit()
    except IntegrityError:
        db.rollback()
        existant = paiement_par_cle(db, demande.usager_id, cle_idempotence)
        if existant is not None:
            return _rejouer(existant, demande), False
        raise ErreurMetier(409, "Un paiement est déjà en cours ou réussi pour cette demande")

    try:
        paiement.id_transaction_operateur = operateur_client.demander_debit(
            paiement.reference, operateur, telephone, paiement.montant
        )
    except OperateurIndisponible:
        log.exception("Opérateur %s injoignable pour le paiement %s", operateur, paiement.reference)
        paiement.statut = StatutPaiement.ECHOUE.value
        paiement.motif = "Opérateur injoignable, veuillez réessayer"
        paiement.maj_le = maintenant()
        db.commit()
        raise ErreurMetier(502, paiement.motif)
    db.commit()
    log.info("Débit demandé : paiement %s, %s FCFA", paiement.reference, paiement.montant)
    return paiement, True


def _rejouer(paiement: Paiement, demande: Demande) -> Paiement:
    if paiement.demande_id != demande.id:
        raise ErreurMetier(422, "Cette clé d'idempotence a déjà servi pour une autre demande")
    return paiement
