"""Logique métier des paiements (indépendante de HTTP)."""
import logging
import uuid
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import config
from ..database import maintenant
from ..erreurs import ErreurMetier
from ..models import Demande, Paiement, StatutDemande, StatutPaiement
from ..operateur import ClientOperateur, OperateurIndisponible
from ..schemas import NotificationOperateur
from ..signature import signature_valide

log = logging.getLogger("paiements")


def lister_pour_demande(db: Session, demande_id: int) -> list[Paiement]:
    expirer_paiements_echus(db, demande_id)
    return list(db.scalars(
        select(Paiement).where(Paiement.demande_id == demande_id).order_by(Paiement.id.desc())
    ))


def paiement_de_l_usager(db: Session, usager_id: int, paiement_id: int) -> Paiement:
    paiement = db.scalar(
        select(Paiement).where(Paiement.id == paiement_id, Paiement.usager_id == usager_id)
    )
    if paiement is None:
        raise ErreurMetier(404, "Paiement introuvable")
    if expirer_paiements_echus(db, paiement.demande_id):
        db.refresh(paiement)
    return paiement


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
        return _rejouer(existant, demande, operateur, telephone), False

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
            return _rejouer(existant, demande, operateur, telephone), False
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


def traiter_notification(db: Session, corps: bytes, signature: str | None) -> Paiement:
    """Applique le résultat transmis par l'opérateur.

    - signature vérifiée sur le corps brut, avant toute lecture ;
    - un paiement REUSSI / ECHOUE ne change plus d'état (renvoi = sans effet) ;
    - UPDATE conditionnel « statut = EN_COURS » : deux notifications simultanées
      ne peuvent pas appliquer deux résultats.
    """
    if not signature_valide(corps, signature, config.OPERATEUR_SECRET):
        log.warning("Notification rejetée : signature invalide")
        raise ErreurMetier(401, "Signature invalide")
    try:
        notification = NotificationOperateur.model_validate_json(corps)
    except ValidationError:
        raise ErreurMetier(422, "Notification mal formée")

    paiement = db.scalar(select(Paiement).where(Paiement.reference == notification.reference))
    if paiement is None:
        raise ErreurMetier(404, "Paiement inconnu")
    if notification.montant != paiement.montant:
        log.error("Montant incohérent pour %s : %s reçu, %s attendu",
                  paiement.reference, notification.montant, paiement.montant)
        raise ErreurMetier(422, "Montant incohérent avec le paiement")
    attendu = paiement.id_transaction_operateur
    if attendu is not None and notification.id_transaction != attendu:
        log.error("Transaction incohérente pour %s : %s reçue, %s attendue",
                  paiement.reference, notification.id_transaction, attendu)
        raise ErreurMetier(422, "Transaction incohérente avec l'accusé de réception")

    # Le délai est dépassé même si personne n'a encore consulté ce paiement.
    if expirer_paiements_echus(db, paiement.demande_id):
        db.refresh(paiement)
    if paiement.statut == StatutPaiement.EXPIRE.value:
        # Le résultat arrive trop tard : on le conserve pour rapprochement, sans changer l'état.
        if paiement.resultat_tardif is None:
            paiement.resultat_tardif = notification.resultat
            db.commit()
        log.error("Résultat tardif %s pour le paiement expiré %s : à rapprocher",
                  notification.resultat, paiement.reference)
        return paiement

    applique = db.execute(
        update(Paiement)
        .where(Paiement.id == paiement.id, Paiement.statut == StatutPaiement.EN_COURS.value)
        .values(
            statut=notification.resultat,
            id_transaction_operateur=notification.id_transaction,
            motif=None if notification.resultat == "REUSSI" else "Débit refusé par l'opérateur",
            maj_le=maintenant(),
        )
    ).rowcount
    if applique and notification.resultat == StatutPaiement.REUSSI.value:
        db.execute(
            update(Demande)
            .where(Demande.id == paiement.demande_id)
            .values(statut=StatutDemande.PAYEE.value)
        )
    db.commit()
    if not applique:
        log.info("Notification déjà traitée pour %s : ignorée", paiement.reference)
    db.refresh(paiement)
    return paiement


def _rejouer(paiement: Paiement, demande: Demande, operateur: str, telephone: str) -> Paiement:
    """Renvoi d'une même clé : on rend le paiement existant, mais seulement si c'est bien
    la même requête. Une clé réutilisée pour autre chose est une erreur du client."""
    if (paiement.demande_id, paiement.operateur, paiement.telephone) != (demande.id, operateur, telephone):
        raise ErreurMetier(422, "Cette clé d'idempotence a déjà servi pour une autre requête")
    return paiement
