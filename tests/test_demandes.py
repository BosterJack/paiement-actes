import pytest

from tests.conftest import creer_demande, inscrire


@pytest.mark.parametrize(
    "type_acte, copies, attendu",
    [
        ("ACTE_NAISSANCE", 1, 1100),
        ("ACTE_NAISSANCE", 3, 3100),
        ("CASIER_JUDICIAIRE", 2, 3100),
        ("CERTIFICAT_RESIDENCE", 1, 600),
    ],
)
def test_montant_calcule_par_le_service(client, type_acte, copies, attendu):
    h = inscrire(client)
    assert creer_demande(client, h, type_acte, copies)["montant"] == attendu


def test_montant_fourni_par_l_usager_refuse(client):
    h = inscrire(client)
    r = client.post(
        "/api/demandes",
        json={"type_acte": "ACTE_NAISSANCE", "nombre_copies": 1, "montant": 1},
        headers=h,
    )
    assert r.status_code == 422
    assert client.get("/api/demandes", headers=h).json() == []


@pytest.mark.parametrize("copies", [0, -1, 21])
def test_nombre_de_copies_invalide(client, copies):
    h = inscrire(client)
    r = client.post(
        "/api/demandes", json={"type_acte": "ACTE_NAISSANCE", "nombre_copies": copies}, headers=h
    )
    assert r.status_code == 422


def test_identification_obligatoire(client):
    assert client.get("/api/demandes").status_code == 401
    assert client.get("/api/demandes", headers={"Authorization": "Bearer faux"}).status_code == 401


def test_usager_ne_voit_pas_la_demande_d_un_autre(client):
    awa = inscrire(client, "Awa")
    kofi = inscrire(client, "Kofi")
    demande = creer_demande(client, awa)
    assert client.get(f"/api/demandes/{demande['id']}", headers=kofi).status_code == 404
    assert client.get("/api/demandes", headers=kofi).json() == []
