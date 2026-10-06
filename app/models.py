from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
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


class StatutPaiement(str, Enum):
    EN_COURS = "EN_COURS"
    REUSSI = "REUSSI"
    ECHOUE = "ECHOUE"
    EXPIRE = "EXPIRE"


STATUTS_FINAUX = {StatutPaiement.REUSSI.value, StatutPaiement.ECHOUE.value, StatutPaiement.EXPIRE.value}

# Un paiement « actif » bloque tout nouveau paiement sur la même demande.
_PAIEMENT_ACTIF = text("statut IN ('EN_COURS', 'REUSSI')")


class Paiement(Base):
    __tablename__ = "paiements"
    __table_args__ = (
        # Idempotence : une même clé envoyée deux fois désigne le même paiement.
        UniqueConstraint("usager_id", "cle_idempotence", name="uq_paiement_cle_idempotence"),
        # Garantie en base (et non dans le code) : au plus un paiement actif par demande,
        # même si deux requêtes arrivent au même instant.
        Index(
            "uq_paiement_actif_par_demande",
            "demande_id",
            unique=True,
            sqlite_where=_PAIEMENT_ACTIF,
            postgresql_where=_PAIEMENT_ACTIF,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Référence transmise à l'opérateur, qui la renvoie dans son résultat.
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    demande_id: Mapped[int] = mapped_column(ForeignKey("demandes.id"), index=True)
    usager_id: Mapped[int] = mapped_column(ForeignKey("usagers.id"), index=True)
    cle_idempotence: Mapped[str] = mapped_column(String(100))
    operateur: Mapped[str] = mapped_column(String(10))
    telephone: Mapped[str] = mapped_column(String(10))
    montant: Mapped[int] = mapped_column(Integer)
    statut: Mapped[str] = mapped_column(String(10), default=StatutPaiement.EN_COURS.value)
    id_transaction_operateur: Mapped[str | None] = mapped_column(String(64), nullable=True)
    motif: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Résultat reçu après expiration : conservé pour rapprochement / remboursement.
    resultat_tardif: Mapped[str | None] = mapped_column(String(10), nullable=True)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
    maj_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
