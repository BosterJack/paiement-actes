from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .operateur import NomOperateur
from .tarifs import TypeActe


class UsagerCreation(BaseModel):
    nom: str = Field(min_length=1, max_length=100)


class UsagerCree(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nom: str
    jeton: str


class TypeActeLu(BaseModel):
    code: TypeActe
    libelle: str
    tarif_unitaire: int


class DemandeCreation(BaseModel):
    # extra="forbid" : un montant envoyé par l'usager est refusé, jamais utilisé.
    model_config = ConfigDict(extra="forbid")

    type_acte: TypeActe
    nombre_copies: int = Field(ge=1, le=20)


class DemandeLue(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type_acte: TypeActe
    nombre_copies: int
    montant: int
    statut: str
    cree_le: datetime


class PaiementCreation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 10 chiffres commençant par 01 ; [0-9] et non \d qui accepterait d'autres chiffres Unicode.
    telephone: str = Field(pattern=r"^01[0-9]{8}$", examples=["0197123456"])
    operateur: NomOperateur


class NotificationOperateur(BaseModel):
    """Message signé envoyé par l'opérateur quand le débit aboutit ou échoue."""

    reference: str
    id_transaction: str
    resultat: Literal["REUSSI", "ECHOUE"]
    montant: int
    horodatage: datetime


class PaiementLu(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    demande_id: int
    operateur: str
    telephone: str
    montant: int
    statut: str
    motif: str | None
    cree_le: datetime
    maj_le: datetime
