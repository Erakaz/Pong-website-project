"""Mots de passe a usage unique (TOTP, RFC 6238) implementes a la main."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

DIGITS = 6
PERIOD = 30
WINDOW = 1
SECRET_BYTES = 20

BACKUP_CODE_COUNT = 10
BACKUP_CODE_BYTES = 5


def generate_secret() -> str:
    """Secret partage, en base32 (le format lisible par les applications)."""
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode("ascii").rstrip("=")


def hotp(secret: str, counter: int, digits: int = DIGITS) -> str:
    """Code a usage unique base sur un compteur (RFC 4226)."""
    padding = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret + padding, casefold=True)

    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()

    offset = digest[-1] & 0x0F
    (value,) = struct.unpack(">I", digest[offset:offset + 4])
    value &= 0x7FFF_FFFF

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
        if hmac.compare_digest(hotp(secret, counter + drift), cleaned):
            valid = True
    return valid


def provisioning_uri(secret: str, account: str, issuer: str = "ft_transcendence") -> str:
    """URI `otpauth://` que le client transforme en QR code."""
    label = quote(f"{issuer}:{account}", safe="")
    return (f"otpauth://totp/{label}"
            f"?secret={secret}&issuer={quote(issuer, safe='')}"
            f"&algorithm=SHA1&digits={DIGITS}&period={PERIOD}")



def generate_backup_codes(count: int = BACKUP_CODE_COUNT) -> list[str]:
    """Codes a usage unique permettant de reprendre la main sans son telephone."""
    codes = []
    for _ in range(count):
        raw = base64.b32encode(secrets.token_bytes(BACKUP_CODE_BYTES)).decode("ascii")
        cleaned = raw.rstrip("=")
        codes.append(f"{cleaned[:4]}-{cleaned[4:]}")
    return codes


def hash_backup_code(code: str) -> str:
    """SHA-256 du code normalise."""
    return hashlib.sha256(normalize_backup_code(code).encode("utf-8")).hexdigest()


def normalize_backup_code(code: str) -> str:
    """Insensible a la casse, aux espaces et aux tirets a la saisie."""
    return "".join(code.split()).replace("-", "").upper()
