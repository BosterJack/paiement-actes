from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .operateur import NomOperateur
from .tarifs import TypeActe


class UsagerCreation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    nom: str = Field(min_length=2, max_length=100)
    # NPI : Numéro Personnel d'Identification, 10 chiffres.
    npi: str = Field(pattern=r"^[0-9]{10}$", examples=["1234567890"])
    email: str = Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", examples=["awa@exemple.bj"])
    mot_de_passe: str = Field(min_length=8, max_length=128)


class Connexion(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    identifiant: str = Field(min_length=1, max_length=255, description="NPI ou email")
    mot_de_passe: str = Field(min_length=1, max_length=128)


class Session(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nom: str
    jeton: str


class UsagerLu(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nom: str
    npi: str
    email: str


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
