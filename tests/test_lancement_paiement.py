import threading

import pytest

from app.services import paiements
from app.models import Demande, Paiement, StatutPaiement
from app.erreurs import ErreurMetier
from tests.conftest import creer_demande, inscrire, payer


def test_paiement_valide_demande_un_debit_du_montant_calcule(client, operateur):
    h = inscrire(client)
    demande = creer_demande(client, h, "CASIER_JUDICIAIRE", 2)
    r = payer(client, h, demande["id"], operateur="MOOV")
    assert r.status_code == 202
    assert r.json()["statut"] == "EN_COURS"
    assert r.json()["montant"] == 3100
    assert operateur.debits == [(r.json()["reference"], "MOOV", "0197000000", 3100)]


def test_montant_fourni_au_paiement_refuse(client, operateur):
    h = inscrire(client)
    demande = creer_demande(client, h)
    r = client.post(
        f"/api/demandes/{demande['id']}/paiements",
        json={"telephone": "0197000000", "operateur": "MTN", "montant": 1},
        headers={**h, "Idempotency-Key": "cle-montant-1"},
    )
    assert r.status_code == 422
    assert operateur.debits == []


@pytest.mark.parametrize(
    "telephone",
    ["019700000", "01970000000", "0297000000", "97000000", "01970000ab", "01 9700000", "", "٠١٩٧٠٠٠٠٠٠"],
)
def test_telephone_invalide_aucun_debit(client, operateur, telephone):
    h = inscrire(client)
    demande = creer_demande(client, h)
    assert payer(client, h, demande["id"], telephone=telephone).status_code == 422
    assert operateur.debits == []


def test_operateur_inconnu_aucun_debit(client, operateur):
    h = inscrire(client)
    demande = creer_demande(client, h)
    assert payer(client, h, demande["id"], operateur="ORANGE").status_code == 422
    assert operateur.debits == []


def test_cle_idempotence_obligatoire(client, operateur):
    h = inscrire(client)
    demande = creer_demande(client, h)
    r = client.post(
        f"/api/demandes/{demande['id']}/paiements",
        json={"telephone": "0197000000", "operateur": "MTN"},
        headers=h,
    )
    assert r.status_code == 422
    assert operateur.debits == []


def test_paiement_en_cours_ne_peut_pas_etre_relance(client, operateur):
    h = inscrire(client)
    demande = creer_demande(client, h)
    assert payer(client, h, demande["id"]).status_code == 202
    r = payer(client, h, demande["id"])
    assert r.status_code == 409
    assert len(operateur.debits) == 1


def test_meme_requete_envoyee_deux_fois_un_seul_debit(client, operateur):
    h = inscrire(client)
    demande = creer_demande(client, h)
    r1 = payer(client, h, demande["id"], cle="reseau-instable-1")
    r2 = payer(client, h, demande["id"], cle="reseau-instable-1")
    assert (r1.status_code, r2.status_code) == (202, 200)
    assert r1.json()["id"] == r2.json()["id"]
    assert len(operateur.debits) == 1


def test_cle_reutilisee_avec_un_autre_numero_refusee(client, operateur):
    h = inscrire(client)
    demande = creer_demande(client, h)
    assert payer(client, h, demande["id"], cle="cle-unique-1").status_code == 202
    r = payer(client, h, demande["id"], telephone="0196111111", cle="cle-unique-1")
    assert r.status_code == 422
    assert len(operateur.debits) == 1


def test_cle_reutilisee_pour_une_autre_demande_refusee(client, operateur):
    h = inscrire(client)
    d1 = creer_demande(client, h)
    d2 = creer_demande(client, h)
    assert payer(client, h, d1["id"], cle="cle-partagee").status_code == 202
    assert payer(client, h, d2["id"], cle="cle-partagee").status_code == 422
    assert len(operateur.debits) == 1


def test_usager_ne_peut_pas_payer_la_demande_d_un_autre(client, operateur):
    awa = inscrire(client, "Awa")
    kofi = inscrire(client, "Kofi")
    demande = creer_demande(client, awa)
    assert payer(client, kofi, demande["id"]).status_code == 404
    assert operateur.debits == []


def test_usager_ne_voit_pas_le_paiement_d_un_autre(client):
    awa = inscrire(client, "Awa")
    kofi = inscrire(client, "Kofi")
    demande = creer_demande(client, awa)
    paiement = payer(client, awa, demande["id"]).json()
    assert client.get(f"/api/paiements/{paiement['id']}", headers=kofi).status_code == 404
    assert client.get(f"/api/demandes/{demande['id']}/paiements", headers=kofi).status_code == 404


def test_operateur_injoignable_paiement_echoue_et_nouvel_essai_possible(client, operateur):
    h = inscrire(client)
    demande = creer_demande(client, h)
    operateur.indisponible = True
    assert payer(client, h, demande["id"]).status_code == 502
    operateur.indisponible = False
    assert payer(client, h, demande["id"]).status_code == 202


def _payer_en_parallele(session_factory, operateur, demande_id, cles):
    """Lance len(cles) paiements exactement au même moment (barrière), un thread chacun."""
    barriere = threading.Barrier(len(cles))
    resultats = []

    def tache(cle):
        db = session_factory()
        try:
            demande = db.get(Demande, demande_id)
            barriere.wait()
            paiement, cree = paiements.lancer_paiement(db, operateur, demande, cle, "MTN", "0197000000")
            resultats.append(("cree" if cree else "rejoue", paiement.id))
        except ErreurMetier as e:
            resultats.append((e.status_code, None))
        finally:
            db.close()

    threads = [threading.Thread(target=tache, args=(c,)) for c in cles]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return resultats


def test_requetes_identiques_simultanees_un_seul_debit(client, session_factory, operateur):
    h = inscrire(client)
    demande = creer_demande(client, h)
    resultats = _payer_en_parallele(session_factory, operateur, demande["id"], ["meme-cle"] * 10)
    assert len(operateur.debits) == 1
    assert sorted(r[0] for r in resultats) == ["cree"] + ["rejoue"] * 9
    assert len({r[1] for r in resultats}) == 1


def test_requetes_differentes_simultanees_sur_une_demande_un_seul_debit(
    client, session_factory, operateur
):
    h = inscrire(client)
    demande = creer_demande(client, h)
    resultats = _payer_en_parallele(
        session_factory, operateur, demande["id"], [f"cle-{i}" for i in range(10)]
    )
    assert len(operateur.debits) == 1
    assert sorted(r[0] for r in resultats if r[0] != 409) == ["cree"]
    db = session_factory()
    actifs = db.query(Paiement).filter(Paiement.statut == StatutPaiement.EN_COURS.value).count()
    db.close()
    assert actifs == 1
