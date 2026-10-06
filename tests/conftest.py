import os
import threading
import uuid

os.environ["SIMULATEUR_AUTO"] = "0"  # les tests pilotent eux-mêmes les résultats

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import Base, creer_engine, get_db
from app.main import app
from app.operateur import OperateurIndisponible, get_operateur


class FauxOperateur:
    """Compte les débits demandés : c'est ce qu'on vérifie (« un seul débit »)."""

    def __init__(self):
        self.debits = []
        self.indisponible = False
        self._verrou = threading.Lock()

    def demander_debit(self, reference, operateur, telephone, montant):
        if self.indisponible:
            raise OperateurIndisponible()
        with self._verrou:
            self.debits.append((reference, operateur, telephone, montant))
        return f"TX-{reference[:8]}"


@pytest.fixture
def operateur():
    return FauxOperateur()


@pytest.fixture
def session_factory(tmp_path):
    # Base SQLite sur fichier : partagée entre threads pour les tests de concurrence.
    engine = creer_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def client(session_factory, operateur):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_operateur] = lambda: operateur
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


MOT_DE_PASSE = "motdepasse-solide"


def inscrire(client, nom="Awa", npi=None, email=None):
    npi = npi or str(uuid.uuid4().int)[:10]
    r = client.post("/api/usagers", json={
        "nom": nom, "npi": npi, "email": email or f"{npi}@exemple.bj", "mot_de_passe": MOT_DE_PASSE,
    })
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['jeton']}"}


def creer_demande(client, headers, type_acte="ACTE_NAISSANCE", copies=2):
    r = client.post(
        "/api/demandes", json={"type_acte": type_acte, "nombre_copies": copies}, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()


def payer(client, headers, demande_id, telephone="0197000000", operateur="MTN", cle=None):
    return client.post(
        f"/api/demandes/{demande_id}/paiements",
        json={"telephone": telephone, "operateur": operateur},
        headers={**headers, "Idempotency-Key": cle or uuid.uuid4().hex},
    )
