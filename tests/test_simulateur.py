"""Bout en bout avec le vrai simulateur : ses messages signés sont acceptés par le service."""
import pytest

from app.operateur import get_operateur
from app.main import app
from app.simulateur import simulateur as module_simulateur
from app.simulateur.simulateur import SimulateurOperateur, resultat_automatique
from tests.conftest import creer_demande, inscrire, payer


@pytest.fixture
def simulateur(client, monkeypatch):
    sim = SimulateurOperateur()
    app.dependency_overrides[get_operateur] = lambda: sim
    monkeypatch.setattr(module_simulateur, "simulateur", sim)

    def poster_via_client_de_test(corps, signature):
        r = client.post("/api/operateur/notifications", content=corps,
                        headers={"X-Signature": signature})
        return {"code_http": r.status_code, "corps": r.json()}

    monkeypatch.setattr(module_simulateur, "poster_notification", poster_via_client_de_test)
    return sim


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
