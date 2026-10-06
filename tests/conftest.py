import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import Base, creer_engine, get_db
from app.main import app


@pytest.fixture
def session_factory(tmp_path):
    # Base SQLite sur fichier : partagée entre threads pour les tests de concurrence.
    engine = creer_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def inscrire(client, nom="Awa"):
    r = client.post("/api/usagers", json={"nom": nom})
    return {"Authorization": f"Bearer {r.json()['jeton']}"}


def creer_demande(client, headers, type_acte="ACTE_NAISSANCE", copies=2):
    r = client.post(
        "/api/demandes", json={"type_acte": type_acte, "nombre_copies": copies}, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()
