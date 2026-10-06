import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import comptes, demandes, routes_paiements
from .database import Base, engine
from .paiements import ErreurMetier
from .simulateur import routes as routes_simulateur

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Paiement des demandes d'actes", lifespan=lifespan)
app.include_router(comptes.router)
app.include_router(demandes.router)
app.include_router(routes_paiements.router)
app.include_router(routes_simulateur.router)


@app.exception_handler(ErreurMetier)
async def erreur_metier(request: Request, exc: ErreurMetier):
    # Même format que les erreurs FastAPI ({"detail": ...}) pour un client unique.
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def accueil():
    return FileResponse(STATIC / "index.html")


@app.get("/health", tags=["supervision"])
def health():
    return {"status": "ok"}
