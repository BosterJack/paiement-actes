"""Pupitre du simulateur : permet au jury de provoquer chaque cas à la main."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import simulateur as module

router = APIRouter(prefix="/simulateur", tags=["simulateur (hors périmètre)"])


class OrdreResultat(BaseModel):
    resultat: Literal["REUSSI", "ECHOUE"]
    signature_valide: bool = True


@router.get("/debits")
def lister_debits():
    return [
        {k: v for k, v in d.items() if k != "dernier_envoi"}
        for d in reversed(list(module.simulateur.debits.values()))
    ]


@router.post("/debits/{reference}/resultat")
def envoyer_resultat(reference: str, ordre: OrdreResultat):
    try:
        return module.simulateur.envoyer_resultat(reference, ordre.resultat, ordre.signature_valide)
    except KeyError:
        raise HTTPException(status_code=404, detail="Débit inconnu du simulateur")


@router.post("/debits/{reference}/renvoyer")
def renvoyer_resultat(reference: str):
    try:
        return module.simulateur.renvoyer(reference)
    except KeyError:
        raise HTTPException(status_code=404, detail="Débit inconnu du simulateur")
    except LookupError as e:
        raise HTTPException(status_code=409, detail=str(e))
