from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import demandes
from .database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Paiement des demandes d'actes", lifespan=lifespan)
app.include_router(demandes.router)


@app.get("/health", tags=["supervision"])
def health():
    return {"status": "ok"}
