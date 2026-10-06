"""Scénario de recette : le parcours complet, dans l'ordre où le jury le déroule,
avec le vrai simulateur d'opérateur (accusé de réception puis résultat signé).

Chaque étape est rattachée au socle ou à la règle de gestion de l'énoncé qu'elle vérifie.
"""
import threading
from datetime import timedelta

from app import config
from app.models import Demande, Paiement
from app.services import paiements as service_paiements
from tests.conftest import MOT_DE_PASSE


def entete(jeton):
    return {"Authorization": f"Bearer {jeton}"}


def payer(client, h, demande_id, telephone, operateur, cle):
    return client.post(
        f"/api/demandes/{demande_id}/paiements",
        json={"telephone": telephone, "operateur": operateur},
        headers={**h, "Idempotency-Key": cle},
    )


def test_scenario_de_recette_complet(client, simulateur, session_factory):
    statut = lambda p: client.get(f"/api/paiements/{p['id']}", headers=awa).json()["statut"]

    # --- Socle 1 : enregistrer une demande et indiquer le montant à payer -------------
    r = client.post("/api/usagers", json={"nom": "Awa Dossou", "npi": "1234567890",
                                          "email": "awa@exemple.bj", "mot_de_passe": MOT_DE_PASSE})
    awa = entete(r.json()["jeton"])
    demande = client.post("/api/demandes", json={"type_acte": "ACTE_NAISSANCE", "nombre_copies": 2},
                          headers=awa).json()
    assert demande["montant"] == 1000 * 2 + 100

    # Règle : le montant est toujours calculé par le service, jamais fourni par l'usager.
    r = client.post("/api/demandes", json={"type_acte": "ACTE_NAISSANCE", "nombre_copies": 2, "montant": 5},
                    headers=awa)
    assert r.status_code == 422

    # --- Règle : téléphone 10 chiffres commençant par 01, aucun débit si invalide -----
    for invalide in ("0297123456", "019712345", "01971234567", "01ABCDEFGH"):
        assert payer(client, awa, demande["id"], invalide, "MTN", f"cle-invalide-{invalide}").status_code == 422
    assert simulateur.debits == {}

    # --- Socle 2 : lancer le paiement (téléphone + opérateur) -------------------------
    r = payer(client, awa, demande["id"], "0197123456", "MTN", "cle-essai-1")
    assert r.status_code == 202
    p1 = r.json()
    assert (p1["statut"], p1["montant"]) == ("EN_COURS", 2100)

    # --- Socle 3 : l'opérateur accuse réception du débit --------------------------------
    assert list(simulateur.debits) == [p1["reference"]]

    # Règle : même requête envoyée deux fois (réseau instable) => un seul débit.
    r = payer(client, awa, demande["id"], "0197123456", "MTN", "cle-essai-1")
    assert (r.status_code, r.json()["id"]) == (200, p1["id"])
    assert len(simulateur.debits) == 1

    # Règle : paiement en cours => impossible de payer une seconde fois.
    assert payer(client, awa, demande["id"], "0197123456", "MTN", "cle-essai-2").status_code == 409
    assert len(simulateur.debits) == 1

    # Règle : seuls les résultats dont la signature est valide sont pris en compte.
    envoi = simulateur.envoyer_resultat(p1["reference"], "REUSSI", signature_valide=False)
    assert envoi["reponse_du_service"]["code_http"] == 401
    assert statut(p1) == "EN_COURS"

    # --- Socle 3 + 4 : résultat signé transmis, pris en compte, état consultable -------
    simulateur.envoyer_resultat(p1["reference"], "ECHOUE")
    assert statut(p1) == "ECHOUE"

    # Règle : un paiement échoué ne change plus d'état, même si le résultat est renvoyé.
    assert simulateur.renvoyer(p1["reference"])["reponse_du_service"]["code_http"] == 200
    simulateur.envoyer_resultat(p1["reference"], "REUSSI")
    assert statut(p1) == "ECHOUE"

    # Règle : après un échec, l'usager doit réessayer.
    p2 = payer(client, awa, demande["id"], "0196000001", "MOOV", "cle-essai-3").json()
    assert p2["statut"] == "EN_COURS" and len(simulateur.debits) == 2
    simulateur.envoyer_resultat(p2["reference"], "REUSSI")
    assert statut(p2) == "REUSSI"
    assert client.get(f"/api/demandes/{demande['id']}", headers=awa).json()["statut"] == "PAYEE"

    # Règle : un paiement réussi ne change plus d'état ; une demande payée ne se repaie pas.
    simulateur.renvoyer(p2["reference"])
    simulateur.envoyer_resultat(p2["reference"], "ECHOUE")
    assert statut(p2) == "REUSSI"
    assert payer(client, awa, demande["id"], "0197123456", "CELTIIS", "cle-essai-4").status_code == 409
    assert len(simulateur.debits) == 2

    # --- Règle : un usager n'agit que sur ses propres demandes et paiements -------------
    kofi = entete(client.post("/api/usagers", json={"nom": "Kofi Agbo", "npi": "9876543210",
                                                    "email": "kofi@exemple.bj", "mot_de_passe": MOT_DE_PASSE}).json()["jeton"])
    assert client.get(f"/api/demandes/{demande['id']}", headers=kofi).status_code == 404
    assert client.get(f"/api/paiements/{p2['id']}", headers=kofi).status_code == 404
    assert payer(client, kofi, demande["id"], "0197123456", "MTN", "cle-kofi-1").status_code == 404

    # --- Règle : deux demandes de paiement identiques au même instant => un seul débit ---
    demande2 = client.post("/api/demandes", json={"type_acte": "CASIER_JUDICIAIRE", "nombre_copies": 1},
                           headers=awa).json()
    barriere = threading.Barrier(5)
    debits_avant = len(simulateur.debits)

    def tentative():
        db = session_factory()
        try:
            d = db.get(Demande, demande2["id"])
            barriere.wait()
            service_paiements.lancer_paiement(db, simulateur, d, "cle-simultanee", "MTN", "0197123456")
        finally:
            db.close()

    threads = [threading.Thread(target=tentative) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(simulateur.debits) == debits_avant + 1

    # --- Règle : paiements dont le résultat n'arrive jamais -----------------------------
    p3 = client.get(f"/api/demandes/{demande2['id']}/paiements", headers=awa).json()[0]
    db = session_factory()
    ancien = db.get(Paiement, p3["id"])
    ancien.cree_le -= timedelta(seconds=config.PAIEMENT_EXPIRATION_SECONDES + 1)
    db.commit()
    db.close()
    assert statut(p3) == "EXPIRE"
    assert payer(client, awa, demande2["id"], "0197123456", "MTN", "cle-apres-expiration").status_code == 202

    # --- Persistance : l'usager se reconnecte (NPI) et retrouve tout son historique ------
    jeton = client.post("/api/sessions", json={"identifiant": "1234567890", "mot_de_passe": MOT_DE_PASSE}).json()["jeton"]
    historique = client.get(f"/api/demandes/{demande['id']}/paiements", headers=entete(jeton)).json()
    assert [p["statut"] for p in historique] == ["REUSSI", "ECHOUE"]
