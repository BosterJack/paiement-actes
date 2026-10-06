import json
import threading
from datetime import datetime, timedelta, timezone

from app import config
from app.models import Paiement
from app.signature import signer
from tests.conftest import creer_demande, inscrire, payer


def notifier(client, paiement, resultat, montant=None, secret=None, signature=None):
    corps = json.dumps(
        {
            "reference": paiement["reference"],
            "id_transaction": "TX-OP-1",
            "resultat": resultat,
            "montant": paiement["montant"] if montant is None else montant,
            "horodatage": datetime.now(timezone.utc).isoformat(),
        }
    ).encode()
    if signature is None:
        signature = signer(corps, secret or config.OPERATEUR_SECRET)
    return client.post(
        "/api/operateur/notifications", content=corps, headers={"X-Signature": signature}
    )


def paiement_en_cours(client, h=None):
    h = h or inscrire(client)
    demande = creer_demande(client, h)
    r = payer(client, h, demande["id"])
    assert r.status_code == 202
    return h, demande, r.json()


def etat(client, h, paiement):
    return client.get(f"/api/paiements/{paiement['id']}", headers=h).json()["statut"]


def test_reussite_marque_paiement_reussi_et_demande_payee(client):
    h, demande, paiement = paiement_en_cours(client)
    assert notifier(client, paiement, "REUSSI").status_code == 200
    assert etat(client, h, paiement) == "REUSSI"
    assert client.get(f"/api/demandes/{demande['id']}", headers=h).json()["statut"] == "PAYEE"


def test_demande_payee_ne_peut_pas_etre_repayee(client, operateur):
    h, demande, paiement = paiement_en_cours(client)
    notifier(client, paiement, "REUSSI")
    r = payer(client, h, demande["id"])
    assert r.status_code == 409
    assert len(operateur.debits) == 1


def test_echec_permet_un_nouvel_essai(client, operateur):
    h, demande, paiement = paiement_en_cours(client)
    assert notifier(client, paiement, "ECHOUE").status_code == 200
    assert etat(client, h, paiement) == "ECHOUE"
    assert client.get(f"/api/demandes/{demande['id']}", headers=h).json()["statut"] == "EN_ATTENTE_PAIEMENT"
    assert payer(client, h, demande["id"]).status_code == 202
    assert len(operateur.debits) == 2


def test_signature_falsifiee_ignoree(client):
    h, demande, paiement = paiement_en_cours(client)
    assert notifier(client, paiement, "REUSSI", secret="mauvais-secret").status_code == 401
    assert notifier(client, paiement, "REUSSI", signature="").status_code == 401
    assert etat(client, h, paiement) == "EN_COURS"


def test_corps_modifie_apres_signature_rejete(client):
    h, demande, paiement = paiement_en_cours(client)
    corps = json.dumps({"reference": paiement["reference"], "id_transaction": "TX",
                        "resultat": "ECHOUE", "montant": paiement["montant"],
                        "horodatage": "2026-10-06T15:00:00Z"}).encode()
    signature = signer(corps, config.OPERATEUR_SECRET)
    corps_modifie = corps.replace(b"ECHOUE", b"REUSSI")
    r = client.post("/api/operateur/notifications", content=corps_modifie,
                    headers={"X-Signature": signature})
    assert r.status_code == 401
    assert etat(client, h, paiement) == "EN_COURS"


def test_resultat_envoye_deux_fois_sans_effet(client):
    h, demande, paiement = paiement_en_cours(client)
    assert notifier(client, paiement, "REUSSI").status_code == 200
    assert notifier(client, paiement, "REUSSI").status_code == 200
    assert etat(client, h, paiement) == "REUSSI"


def test_resultat_final_ne_change_plus(client):
    h, demande, paiement = paiement_en_cours(client)
    notifier(client, paiement, "ECHOUE")
    assert notifier(client, paiement, "REUSSI").status_code == 200
    assert etat(client, h, paiement) == "ECHOUE"
    assert client.get(f"/api/demandes/{demande['id']}", headers=h).json()["statut"] == "EN_ATTENTE_PAIEMENT"


def test_notifications_contradictoires_simultanees_un_seul_resultat(client):
    h, demande, paiement = paiement_en_cours(client)
    barriere = threading.Barrier(2)

    def envoyer(resultat):
        barriere.wait()
        notifier(client, paiement, resultat)

    threads = [threading.Thread(target=envoyer, args=(r,)) for r in ("REUSSI", "ECHOUE")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    statut = etat(client, h, paiement)
    demande_statut = client.get(f"/api/demandes/{demande['id']}", headers=h).json()["statut"]
    assert (statut, demande_statut) in {("REUSSI", "PAYEE"), ("ECHOUE", "EN_ATTENTE_PAIEMENT")}


def test_montant_incoherent_rejete(client):
    h, demande, paiement = paiement_en_cours(client)
    assert notifier(client, paiement, "REUSSI", montant=1).status_code == 422
    assert etat(client, h, paiement) == "EN_COURS"


def test_reference_inconnue(client):
    r = notifier(client, {"reference": "inconnue", "montant": 100}, "REUSSI")
    assert r.status_code == 404


def _vieillir(session_factory, paiement, secondes):
    db = session_factory()
    p = db.get(Paiement, paiement["id"])
    p.cree_le = p.cree_le - timedelta(seconds=secondes)
    db.commit()
    db.close()


def test_resultat_jamais_recu_paiement_expire_et_nouvel_essai(client, session_factory, operateur):
    h, demande, paiement = paiement_en_cours(client)
    assert etat(client, h, paiement) == "EN_COURS"
    _vieillir(session_factory, paiement, config.PAIEMENT_EXPIRATION_SECONDES + 1)
    assert etat(client, h, paiement) == "EXPIRE"
    assert payer(client, h, demande["id"]).status_code == 202
    assert len(operateur.debits) == 2


def test_resultat_tardif_apres_expiration_conserve_sans_changer_l_etat(client, session_factory):
    h, demande, paiement = paiement_en_cours(client)
    _vieillir(session_factory, paiement, config.PAIEMENT_EXPIRATION_SECONDES + 1)
    # Aucune consultation avant le résultat : il doit quand même être traité comme tardif.
    assert notifier(client, paiement, "REUSSI").status_code == 200
    assert etat(client, h, paiement) == "EXPIRE"
    db = session_factory()
    assert db.get(Paiement, paiement["id"]).resultat_tardif == "REUSSI"
    db.close()
