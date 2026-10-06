from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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
