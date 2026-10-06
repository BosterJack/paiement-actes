"""Grille tarifaire : la seule source de vérité pour le montant à payer."""
from enum import Enum


class TypeActe(str, Enum):
    ACTE_NAISSANCE = "ACTE_NAISSANCE"
    CASIER_JUDICIAIRE = "CASIER_JUDICIAIRE"
    CERTIFICAT_RESIDENCE = "CERTIFICAT_RESIDENCE"


LIBELLES = {
    TypeActe.ACTE_NAISSANCE: "Acte de naissance",
    TypeActe.CASIER_JUDICIAIRE: "Casier judiciaire",
    TypeActe.CERTIFICAT_RESIDENCE: "Certificat de résidence",
}

# Montants en FCFA (entiers : le franc CFA n'a pas de subdivision).
TARIFS_UNITAIRES = {
    TypeActe.ACTE_NAISSANCE: 1000,
    TypeActe.CASIER_JUDICIAIRE: 1500,
    TypeActe.CERTIFICAT_RESIDENCE: 500,
}
FRAIS_SERVICE = 100


def calculer_montant(type_acte: TypeActe, nombre_copies: int) -> int:
    return TARIFS_UNITAIRES[type_acte] * nombre_copies + FRAIS_SERVICE
