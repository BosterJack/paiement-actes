"""Garanties portées par la base et gestion des erreurs inattendues."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.models import Demande, Paiement, Usager
from app.services import demandes as service_demandes
from tests.conftest import creer_demande, inscrire


def _demande_en_base(session_factory, client):
    h = inscrire(client)
    return creer_demande(client, h)


@pytest.mark.parametrize("champ, valeur", [
    ("statut", "PAYE_PEUT_ETRE"), ("operateur", "ORANGE"), ("montant", 0),
])
def test_la_base_refuse_un_paiement_incoherent(client, session_factory, champ, valeur):
    demande = _demande_en_base(session_factory, client)
    db = session_factory()
    valeurs = dict(reference="r" * 32, demande_id=demande["id"], usager_id=1, cle_idempotence="cle-test",
                   operateur="MTN", telephone="0197123456", montant=1100)
    db.add(Paiement(**{**valeurs, champ: valeur}))
    with pytest.raises(IntegrityError):
        db.commit()
    db.close()


@pytest.mark.parametrize("champ, valeur", [("nombre_copies", 0), ("montant", -5), ("statut", "GRATUITE")])
def test_la_base_refuse_une_demande_incoherente(client, session_factory, champ, valeur):
    inscrire(client)
    db = session_factory()
    valeurs = dict(usager_id=db.query(Usager).first().id, type_acte="ACTE_NAISSANCE", nombre_copies=1, montant=1100)
    db.add(Demande(**{**valeurs, champ: valeur}))
    with pytest.raises(IntegrityError):
        db.commit()
    db.close()


def test_erreur_inattendue_renvoie_500_sans_detail_technique(client, monkeypatch):
    h = inscrire(client)

    def panne(*args, **kwargs):
        raise RuntimeError("connexion base perdue : mot de passe=secret")

    monkeypatch.setattr(service_demandes, "lister", panne)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/demandes", headers=h)
    assert r.status_code == 500
    assert r.json() == {"detail": "Erreur interne, veuillez réessayer"}
