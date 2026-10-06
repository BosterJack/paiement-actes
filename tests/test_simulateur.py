"""Bout en bout avec le vrai simulateur : ses messages signés sont acceptés par le service."""
import pytest

from app.simulateur.simulateur import resultat_automatique
from tests.conftest import creer_demande, inscrire, payer


def lancer(client):
    h = inscrire(client)
    demande = creer_demande(client, h)
    paiement = payer(client, h, demande["id"]).json()
    return h, paiement


def statut(client, h, paiement):
    return client.get(f"/api/paiements/{paiement['id']}", headers=h).json()["statut"]


def test_simulateur_accuse_reception(client, simulateur):
    h, paiement = lancer(client)
    debits = client.get("/simulateur/debits").json()
    assert [d["reference"] for d in debits] == [paiement["reference"]]


def test_simulateur_reussite(client, simulateur):
    h, paiement = lancer(client)
    r = client.post(f"/simulateur/debits/{paiement['reference']}/resultat", json={"resultat": "REUSSI"})
    assert r.json()["reponse_du_service"]["code_http"] == 200
    assert statut(client, h, paiement) == "REUSSI"


def test_simulateur_signature_falsifiee_rejetee(client, simulateur):
    h, paiement = lancer(client)
    r = client.post(f"/simulateur/debits/{paiement['reference']}/resultat",
                    json={"resultat": "REUSSI", "signature_valide": False})
    assert r.json()["reponse_du_service"]["code_http"] == 401
    assert statut(client, h, paiement) == "EN_COURS"


def test_simulateur_renvoi_identique_sans_effet(client, simulateur):
    h, paiement = lancer(client)
    client.post(f"/simulateur/debits/{paiement['reference']}/resultat", json={"resultat": "ECHOUE"})
    r = client.post(f"/simulateur/debits/{paiement['reference']}/renvoyer")
    assert r.json()["reponse_du_service"]["code_http"] == 200
    assert statut(client, h, paiement) == "ECHOUE"


@pytest.mark.parametrize(
    "telephone, attendu", [("0197000000", "ECHOUE"), ("0197000099", None), ("0197123456", "REUSSI")]
)
def test_regles_du_mode_automatique(telephone, attendu):
    assert resultat_automatique(telephone) == attendu


@pytest.mark.parametrize(
    "mode, attendu", [("REUSSITE", "REUSSI"), ("ECHEC", "ECHOUE"), ("MANUEL", None)]
)
def test_modes_forces_ignorent_le_numero(mode, attendu):
    for telephone in ("0197000000", "0197000099", "0197123456"):
        assert resultat_automatique(telephone, mode) == attendu


def test_changer_de_mode(client, simulateur):
    assert client.get("/simulateur/mode").json() == {"mode": "NUMERO"}
    assert client.put("/simulateur/mode", json={"mode": "ECHEC"}).json() == {"mode": "ECHEC"}
    assert simulateur.mode == "ECHEC"
    assert client.put("/simulateur/mode", json={"mode": "N_IMPORTE_QUOI"}).status_code == 422
