"""Contrat entre le service de paiement et un opérateur de paiement mobile."""
from enum import Enum
from typing import Protocol


class NomOperateur(str, Enum):
    MTN = "MTN"
    MOOV = "MOOV"
    CELTIIS = "CELTIIS"


class OperateurIndisponible(Exception):
    pass


class ClientOperateur(Protocol):
    def demander_debit(
        self, reference: str, operateur: str, telephone: str, montant: int
    ) -> str:
        """Demande un débit. Retourne l'identifiant de transaction de l'accusé de réception.

        L'accusé confirme seulement la réception de la demande : le résultat (réussite
        ou échec) arrive plus tard, par une notification signée.
        """
        ...


def get_operateur() -> ClientOperateur:
    # Seul le simulateur existe dans cette épreuve ; un vrai client HTTP le remplacerait ici.
    from .simulateur.simulateur import simulateur

    return simulateur
