import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .erreurs import installer_gestionnaires
from .routes import comptes, demandes, operateur, paiements
from .simulateur import routes as simulateur

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Paiement des demandes d'actes", version="1.0.0", lifespan=lifespan)
installer_gestionnaires(app)
for module in (comptes, demandes, paiements, operateur, simulateur):
    app.include_router(module.router)

STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def accueil():
    return FileResponse(STATIC / "index.html")


@app.get("/health", tags=["supervision"])
def health():
    return {"status": "ok"}
