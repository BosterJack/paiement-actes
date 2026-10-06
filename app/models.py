from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, maintenant


class StatutDemande(str, Enum):
    EN_ATTENTE_PAIEMENT = "EN_ATTENTE_PAIEMENT"
    PAYEE = "PAYEE"


class Usager(Base):
    __tablename__ = "usagers"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(100))
    jeton: Mapped[str] = mapped_column(String(64), unique=True, index=True)


class Demande(Base):
    __tablename__ = "demandes"

    id: Mapped[int] = mapped_column(primary_key=True)
    usager_id: Mapped[int] = mapped_column(ForeignKey("usagers.id"), index=True)
    type_acte: Mapped[str] = mapped_column(String(30))
    nombre_copies: Mapped[int] = mapped_column(Integer)
    montant: Mapped[int] = mapped_column(Integer)
    statut: Mapped[str] = mapped_column(String(30), default=StatutDemande.EN_ATTENTE_PAIEMENT.value)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
