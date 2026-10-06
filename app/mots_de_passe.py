"""Hachage des mots de passe avec scrypt (bibliothèque standard, résistant à la force brute)."""
import hashlib
import hmac
import secrets

_N, _R, _P = 2**14, 8, 1


def hacher(mot_de_passe: str) -> str:
    sel = secrets.token_bytes(16)
    empreinte = hashlib.scrypt(mot_de_passe.encode(), salt=sel, n=_N, r=_R, p=_P)
    return f"scrypt${sel.hex()}${empreinte.hex()}"


def verifier(mot_de_passe: str, hache: str) -> bool:
    try:
        _, sel, empreinte = hache.split("$")
    except ValueError:
        return False
    calcule = hashlib.scrypt(mot_de_passe.encode(), salt=bytes.fromhex(sel), n=_N, r=_R, p=_P)
    return hmac.compare_digest(calcule.hex(), empreinte)


# Haché factice : même coût de calcul quand l'identifiant n'existe pas,
# pour ne pas révéler par le temps de réponse quels comptes existent.
HACHE_FACTICE = hacher(secrets.token_hex(16))
