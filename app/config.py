"""Configuration lue depuis les variables d'environnement (valeurs par défaut pour la démo)."""
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./paiement_actes.db")

# Secret partagé avec l'opérateur pour signer (HMAC-SHA256) ses notifications.
OPERATEUR_SECRET = os.getenv("OPERATEUR_SECRET", "secret-partage-demo")

# Adresse à laquelle le simulateur d'opérateur envoie ses résultats.
URL_NOTIFICATION = os.getenv(
    "URL_NOTIFICATION", "http://127.0.0.1:8000/api/operateur/notifications"
)

# Au-delà de ce délai sans résultat de l'opérateur, un paiement en cours expire.
PAIEMENT_EXPIRATION_SECONDES = int(os.getenv("PAIEMENT_EXPIRATION_SECONDES", "120"))

# Délai avant que le simulateur envoie automatiquement son résultat.
SIMULATEUR_DELAI_SECONDES = float(os.getenv("SIMULATEUR_DELAI_SECONDES", "3"))
SIMULATEUR_AUTO = os.getenv("SIMULATEUR_AUTO", "1") == "1"
