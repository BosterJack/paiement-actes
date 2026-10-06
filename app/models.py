"""Modèle de données. Les invariants critiques sont garantis par la base elle-même
(contraintes CHECK et UNIQUE), pas seulement par le code applicatif."""
from datetime import datetime
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, maintenant


def _valeurs(enum: type[Enum]) -> str:
    return ", ".join(f"'{e.value}'" for e in enum)


class StatutDemande(str, Enum):
    EN_ATTENTE_PAIEMENT = "EN_ATTENTE_PAIEMENT"
    PAYEE = "PAYEE"


class StatutPaiement(str, Enum):
    EN_COURS = "EN_COURS"
    REUSSI = "REUSSI"
    ECHOUE = "ECHOUE"
    EXPIRE = "EXPIRE"


class Usager(Base):
    __tablename__ = "usagers"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(100))
    npi: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    mot_de_passe_hache: Mapped[str] = mapped_column(String(200))
    jeton: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)


class Demande(Base):
    __tablename__ = "demandes"
    __table_args__ = (
        CheckConstraint("nombre_copies BETWEEN 1 AND 20", name="ck_demande_copies"),
        CheckConstraint("montant > 0", name="ck_demande_montant"),
        CheckConstraint(f"statut IN ({_valeurs(StatutDemande)})", name="ck_demande_statut"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usager_id: Mapped[int] = mapped_column(ForeignKey("usagers.id"), index=True)
    type_acte: Mapped[str] = mapped_column(String(30))
    nombre_copies: Mapped[int] = mapped_column(Integer)
    # Montant en FCFA (entier), calculé par le service à la création et figé ensuite.
    montant: Mapped[int] = mapped_column(Integer)
    statut: Mapped[str] = mapped_column(String(30), default=StatutDemande.EN_ATTENTE_PAIEMENT.value)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)


# Un paiement « actif » bloque tout nouveau paiement sur la même demande.
_PAIEMENT_ACTIF = text("statut IN ('EN_COURS', 'REUSSI')")


class Paiement(Base):
    """Une tentative de paiement d'une demande. Une demande peut en avoir plusieurs
    (après un échec ou une expiration), mais jamais deux actives en même temps."""

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
        # Recherche des paiements EN_COURS trop anciens (expiration).
        Index("ix_paiement_statut_cree_le", "statut", "cree_le"),
        CheckConstraint(f"statut IN ({_valeurs(StatutPaiement)})", name="ck_paiement_statut"),
        CheckConstraint("operateur IN ('MTN', 'MOOV', 'CELTIIS')", name="ck_paiement_operateur"),
        CheckConstraint("montant > 0", name="ck_paiement_montant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Référence transmise à l'opérateur, qui la renvoie dans son résultat.
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    demande_id: Mapped[int] = mapped_column(ForeignKey("demandes.id"), index=True)
    usager_id: Mapped[int] = mapped_column(ForeignKey("usagers.id"), index=True)
    cle_idempotence: Mapped[str] = mapped_column(String(100))
    operateur: Mapped[str] = mapped_column(String(10))
    telephone: Mapped[str] = mapped_column(String(10))
    # Copie du montant de la demande au moment du paiement : c'est ce qui a été débité.
    montant: Mapped[int] = mapped_column(Integer)
    statut: Mapped[str] = mapped_column(String(10), default=StatutPaiement.EN_COURS.value)
    # Identifiant donné par l'opérateur dans son accusé de réception.
    id_transaction_operateur: Mapped[str | None] = mapped_column(String(64), nullable=True)
    motif: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Résultat reçu après expiration : conservé pour rapprochement / remboursement.
    resultat_tardif: Mapped[str | None] = mapped_column(String(10), nullable=True)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
    maj_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
