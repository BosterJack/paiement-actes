"""Signature HMAC-SHA256 des notifications de l'opérateur (secret partagé)."""
import hashlib
import hmac


def signer(corps: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()


def signature_valide(corps: bytes, signature: str | None, secret: str) -> bool:
    if not signature:
        return False
    # compare_digest : comparaison à temps constant, pas d'attaque par mesure du temps.
    return hmac.compare_digest(signer(corps, secret), signature)
