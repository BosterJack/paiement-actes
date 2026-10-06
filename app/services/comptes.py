"""Inscription et authentification des usagers (NPI ou email + mot de passe)."""
import secrets

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import mots_de_passe
from ..erreurs import ErreurMetier
from ..models import Usager
from ..schemas import UsagerCreation

DEJA_INSCRIT = "Un compte existe déjà avec ce NPI ou cet email"
IDENTIFIANTS_INCORRECTS = "Identifiant ou mot de passe incorrect"


def inscrire(db: Session, data: UsagerCreation) -> Usager:
    email = data.email.lower()
    if db.scalar(select(Usager).where(or_(Usager.npi == data.npi, Usager.email == email))):
        raise ErreurMetier(409, DEJA_INSCRIT)
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
        raise ErreurMetier(409, DEJA_INSCRIT)
    return usager


def authentifier(db: Session, identifiant: str, mot_de_passe: str) -> Usager:
    identifiant = identifiant.lower()
    usager = db.scalar(
        select(Usager).where(or_(Usager.npi == identifiant, Usager.email == identifiant))
    )
    # Haché factice si le compte n'existe pas : même temps de calcul, même message,
    # on ne révèle pas quels NPI / emails sont inscrits.
    hache = usager.mot_de_passe_hache if usager else mots_de_passe.HACHE_FACTICE
    if not mots_de_passe.verifier(mot_de_passe, hache) or usager is None:
        raise ErreurMetier(401, IDENTIFIANTS_INCORRECTS)
    return usager
