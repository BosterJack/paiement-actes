import pytest

from tests.conftest import MOT_DE_PASSE, creer_demande, inscrire, payer


def connecter(client, identifiant, mot_de_passe=MOT_DE_PASSE):
    return client.post("/api/sessions", json={"identifiant": identifiant, "mot_de_passe": mot_de_passe})


def test_reconnexion_par_npi_ou_email_retrouve_ses_paiements(client):
    h = inscrire(client, "Awa Dossou", npi="1234567890", email="Awa@Exemple.bj")
    demande = creer_demande(client, h)
    payer(client, h, demande["id"])

    for identifiant in ("1234567890", "awa@exemple.bj", "AWA@exemple.bj"):
        r = connecter(client, identifiant)
        assert r.status_code == 200
        h2 = {"Authorization": f"Bearer {r.json()['jeton']}"}
        assert [d["id"] for d in client.get("/api/demandes", headers=h2).json()] == [demande["id"]]
        assert len(client.get(f"/api/demandes/{demande['id']}/paiements", headers=h2).json()) == 1


def test_profil(client):
    h = inscrire(client, "Awa Dossou", npi="1234567890", email="awa@exemple.bj")
    assert client.get("/api/usagers/moi", headers=h).json() == {
        "id": 1, "nom": "Awa Dossou", "npi": "1234567890", "email": "awa@exemple.bj"
    }


@pytest.mark.parametrize("identifiant, mot_de_passe", [
    ("1234567890", "mauvais-mot-de-passe"),
    ("0000000000", MOT_DE_PASSE),
    ("inconnu@exemple.bj", MOT_DE_PASSE),
])
def test_connexion_refusee_meme_message(client, identifiant, mot_de_passe):
    inscrire(client, npi="1234567890")
    r = connecter(client, identifiant, mot_de_passe)
    assert r.status_code == 401
    assert r.json()["detail"] == "Identifiant ou mot de passe incorrect"


def test_npi_ou_email_deja_utilise(client):
    inscrire(client, npi="1234567890", email="awa@exemple.bj")
    base = {"nom": "Autre", "mot_de_passe": MOT_DE_PASSE}
    assert client.post("/api/usagers", json={**base, "npi": "1234567890", "email": "x@exemple.bj"}).status_code == 409
    assert client.post("/api/usagers", json={**base, "npi": "9999999999", "email": "AWA@exemple.bj"}).status_code == 409


@pytest.mark.parametrize("champ, valeur", [
    ("npi", "123456789"), ("npi", "12345678901"), ("npi", "12345abcde"),
    ("email", "pas-un-email"), ("mot_de_passe", "court"), ("nom", " "),
])
def test_inscription_invalide(client, champ, valeur):
    corps = {"nom": "Awa", "npi": "1234567890", "email": "awa@exemple.bj", "mot_de_passe": MOT_DE_PASSE}
    assert client.post("/api/usagers", json={**corps, champ: valeur}).status_code == 422


def test_mot_de_passe_jamais_stocke_en_clair(client, session_factory):
    from app.models import Usager

    inscrire(client, npi="1234567890")
    db = session_factory()
    hache = db.query(Usager).one().mot_de_passe_hache
    db.close()
    assert MOT_DE_PASSE not in hache and hache.startswith("scrypt$")
