"""Simulateur d'opérateur de paiement mobile (hors périmètre évalué, volontairement simple).

1. demander_debit : accuse réception immédiatement (identifiant de transaction).
2. Plus tard, envoie le résultat signé à l'URL de notification du service.

Mode automatique, selon les 2 derniers chiffres du téléphone :
  ...00 -> échec ; ...99 -> aucune réponse ; sinon -> réussite.
"""
import json
import logging
import threading
import uuid
from datetime import datetime, timezone

import httpx

from .. import config
from ..signature import signer

log = logging.getLogger("simulateur")


class SimulateurOperateur:
    def __init__(self):
        self.debits: dict[str, dict] = {}
        self._verrou = threading.Lock()

    def demander_debit(self, reference: str, operateur: str, telephone: str, montant: int) -> str:
        id_transaction = f"{operateur}-{uuid.uuid4().hex[:10].upper()}"
        with self._verrou:
            self.debits[reference] = {
                "reference": reference,
                "id_transaction": id_transaction,
                "operateur": operateur,
                "telephone": telephone,
                "montant": montant,
                "dernier_envoi": None,
                "envois": [],
            }
        log.info("Accusé de réception : débit %s de %s FCFA sur %s", id_transaction, montant, telephone)
        if config.SIMULATEUR_AUTO:
            resultat = resultat_automatique(telephone)
            if resultat is not None:
                minuteur = threading.Timer(
                    config.SIMULATEUR_DELAI_SECONDES, self._envoyer_sans_erreur, args=(reference, resultat)
                )
                minuteur.daemon = True
                minuteur.start()
        return id_transaction

    def envoyer_resultat(self, reference: str, resultat: str, signature_valide: bool = True) -> dict:
        debit = self._debit(reference)
        corps = json.dumps(
            {
                "reference": reference,
                "id_transaction": debit["id_transaction"],
                "resultat": resultat,
                "montant": debit["montant"],
                "horodatage": datetime.now(timezone.utc).isoformat(),
            }
        ).encode()
        secret = config.OPERATEUR_SECRET if signature_valide else "secret-d-un-imposteur"
        signature = signer(corps, secret)
        if signature_valide:
            debit["dernier_envoi"] = (corps, signature)
        return self._livrer(debit, corps, signature, "valide" if signature_valide else "falsifiée")

    def renvoyer(self, reference: str) -> dict:
        """Renvoie à l'identique (mêmes octets, même signature) le dernier résultat valide."""
        debit = self._debit(reference)
        if debit["dernier_envoi"] is None:
            raise LookupError("Aucun résultat valide n'a encore été envoyé pour ce débit")
        corps, signature = debit["dernier_envoi"]
        return self._livrer(debit, corps, signature, "valide (renvoi)")

    def _debit(self, reference: str) -> dict:
        with self._verrou:
            debit = self.debits.get(reference)
        if debit is None:
            raise KeyError(reference)
        return debit

    def _livrer(self, debit: dict, corps: bytes, signature: str, type_signature: str) -> dict:
        reponse = poster_notification(corps, signature)
        envoi = {
            "resultat": json.loads(corps)["resultat"],
            "signature": type_signature,
            "reponse_du_service": reponse,
        }
        debit["envois"].append(envoi)
        log.info("Résultat envoyé pour %s : %s", debit["reference"], envoi)
        return envoi

    def _envoyer_sans_erreur(self, reference: str, resultat: str) -> None:
        try:
            self.envoyer_resultat(reference, resultat)
        except Exception:
            log.exception("Envoi automatique impossible pour %s", reference)


def resultat_automatique(telephone: str) -> str | None:
    if telephone.endswith("99"):
        return None
    if telephone.endswith("00"):
        return "ECHOUE"
    return "REUSSI"


def poster_notification(corps: bytes, signature: str) -> dict:
    r = httpx.post(
        config.URL_NOTIFICATION,
        content=corps,
        headers={"Content-Type": "application/json", "X-Signature": signature},
        timeout=5,
    )
    return {"code_http": r.status_code, "corps": r.json()}


simulateur = SimulateurOperateur()
