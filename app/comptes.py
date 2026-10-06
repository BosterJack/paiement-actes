"""Inscription et connexion des usagers (NPI ou email + mot de passe)."""
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as SessionDB

from . import mots_de_passe
from .database import get_db
from .models import Usager
from .schemas import Connexion, Session, UsagerCreation, UsagerLu
from .securite import usager_courant

router = APIRouter(prefix="/api", tags=["comptes"])

DEJA_INSCRIT = "Un compte existe déjà avec ce NPI ou cet email"


@router.post("/usagers", response_model=Session, status_code=status.HTTP_201_CREATED)
def inscrire(data: UsagerCreation, db: SessionDB = Depends(get_db)):
    email = data.email.lower()
    if db.scalar(select(Usager).where(or_(Usager.npi == data.npi, Usager.email == email))):
        raise HTTPException(status_code=409, detail=DEJA_INSCRIT)
    usager = Usager(
        nom=data.nom,
        npi=data.npi,
        email=email,
        mot_de_passe_hache=mots_de_passe.hacher(data.mot_de_passe),
        jeton=secrets.token_urlsafe(32),
    )
    db.add(usager)
    try:
        db.commit()
    except IntegrityError:  # inscription simultanée avec le même NPI / email
        db.rollback()
        raise HTTPException(status_code=409, detail=DEJA_INSCRIT)
    return usager


@router.post("/sessions", response_model=Session)
def se_connecter(data: Connexion, db: SessionDB = Depends(get_db)):
    identifiant = data.identifiant.lower()
    usager = db.scalar(
        select(Usager).where(or_(Usager.npi == identifiant, Usager.email == identifiant))
    )
    hache = usager.mot_de_passe_hache if usager else mots_de_passe.HACHE_FACTICE
    if not mots_de_passe.verifier(data.mot_de_passe, hache) or usager is None:
        # Même message dans les deux cas : on ne révèle pas si le compte existe.
        raise HTTPException(status_code=401, detail="Identifiant ou mot de passe incorrect")
    return usager


@router.get("/usagers/moi", response_model=UsagerLu)
def moi(usager: Usager = Depends(usager_courant)):
    return usager
