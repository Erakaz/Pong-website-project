"""Mots de passe a usage unique (TOTP, RFC 6238) implementes a la main.

Le module « 2FA + JWT » demande d'implementer la double authentification :
appeler `pyotp` reviendrait a ne rien implementer. L'algorithme tient en une
vingtaine de lignes et n'utilise que la bibliotheque standard.

Principe : un compteur derive du temps (nombre de tranches de 30 secondes
ecoulees depuis 1970) est signe en HMAC-SHA1 avec un secret partage, puis
tronque en un nombre a six chiffres. Le serveur et l'application
d'authentification calculent la meme chose, chacun de leur cote, sans jamais
echanger autre chose que le secret initial.

Deux precautions qui distinguent une implementation correcte d'une
implementation dangereuse :

* **fenetre de tolerance** — l'horloge du telephone derive toujours un peu, on
  accepte donc la tranche precedente et la suivante ; pas davantage, sinon la
  duree de validite d'un code s'allonge inutilement ;
* **comparaison en temps constant** — un `==` sur les chaines s'arrete au
  premier caractere different et laisse deviner le code chiffre par chiffre.

La conformite est verifiee dans les tests contre les vecteurs officiels de
l'annexe B de la RFC 6238.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

# Parametres standard, ceux qu'attendent Google Authenticator, Aegis, 1Password
# et les autres applications d'authentification.
DIGITS = 6
PERIOD = 30            # secondes par tranche
WINDOW = 1             # tranches acceptees de part et d'autre
SECRET_BYTES = 20      # 160 bits, la taille recommandee par la RFC 4226

BACKUP_CODE_COUNT = 10
BACKUP_CODE_BYTES = 5  # 40 bits d'entropie, rendus en 8 caracteres base32


def generate_secret() -> str:
    """Secret partage, en base32 (le format lisible par les applications)."""
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode("ascii").rstrip("=")


def hotp(secret: str, counter: int, digits: int = DIGITS) -> str:
    """Code a usage unique base sur un compteur (RFC 4226)."""
    padding = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret + padding, casefold=True)

    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()

    # Troncature dynamique : les quatre bits de poids faible du dernier octet
    # designent l'endroit ou lire les quatre octets qui donneront le code.
    offset = digest[-1] & 0x0F
    (value,) = struct.unpack(">I", digest[offset:offset + 4])
    value &= 0x7FFF_FFFF      # on force le bit de signe a zero

    return str(value % (10 ** digits)).zfill(digits)


def totp(secret: str, at: float | None = None, digits: int = DIGITS,
         period: int = PERIOD) -> str:
    """Code valable pour la tranche de temps courante (RFC 6238)."""
    moment = time.time() if at is None else at
    return hotp(secret, int(moment // period), digits=digits)


def verify(secret: str, code: str, at: float | None = None, window: int = WINDOW) -> bool:
    """Verifie un code, avec tolerance sur la derive d'horloge."""
    if not secret or not isinstance(code, str):
        return False

    cleaned = code.strip().replace(" ", "")
    if not cleaned.isdigit() or len(cleaned) != DIGITS:
        return False

    moment = time.time() if at is None else at
    counter = int(moment // PERIOD)

    valid = False
    for drift in range(-window, window + 1):
        # Pas de sortie anticipee : on parcourt toute la fenetre meme apres
        # avoir trouve, pour que la duree de la verification ne depende pas de
        # la tranche qui a valide.
        if hmac.compare_digest(hotp(secret, counter + drift), cleaned):
            valid = True
    return valid


def provisioning_uri(secret: str, account: str, issuer: str = "ft_transcendence") -> str:
    """URI `otpauth://` que le client transforme en QR code.

    Ce format est celui que lisent toutes les applications d'authentification.
    Il n'est jamais transmis a un service tiers : le QR est dessine dans le
    navigateur, a partir de cette chaine.
    """
    label = quote(f"{issuer}:{account}", safe="")
    return (f"otpauth://totp/{label}"
            f"?secret={secret}&issuer={quote(issuer, safe='')}"
            f"&algorithm=SHA1&digits={DIGITS}&period={PERIOD}")


# --- Codes de secours -------------------------------------------------------

def generate_backup_codes(count: int = BACKUP_CODE_COUNT) -> list[str]:
    """Codes a usage unique permettant de reprendre la main sans son telephone."""
    codes = []
    for _ in range(count):
        raw = base64.b32encode(secrets.token_bytes(BACKUP_CODE_BYTES)).decode("ascii")
        cleaned = raw.rstrip("=")
        codes.append(f"{cleaned[:4]}-{cleaned[4:]}")
    return codes


def hash_backup_code(code: str) -> str:
    """SHA-256 du code normalise.

    Un simple SHA-256 suffit ici, la ou un mot de passe exigerait Argon2 : ces
    codes sont tires au hasard avec 40 bits d'entropie, ils ne sont pas
    devinables par dictionnaire. C'est le meme raisonnement que pour les jetons
    de rafraichissement.
    """
    return hashlib.sha256(normalize_backup_code(code).encode("utf-8")).hexdigest()


def normalize_backup_code(code: str) -> str:
    """Insensible a la casse, aux espaces et aux tirets a la saisie."""
    return "".join(code.split()).replace("-", "").upper()
