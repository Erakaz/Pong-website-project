"""JSON Web Tokens (HS256) implementes a la main.

Le module « 2FA + JWT » demande de maitriser l'emission et la validation des
jetons : deleguer a PyJWT reviendrait a ne rien implementer du module. Le code
tient en une centaine de lignes et suit la RFC 7519 pour la partie utile
(en-tete, charge utile, signature detachee en base64url).

Trois garde-fous qui font la difference entre un JWT correct et un JWT
dangereux :

1. l'algorithme est impose par le serveur, jamais lu depuis l'en-tete du jeton
   — sinon un attaquant renvoie `{"alg": "none"}` et se signe ses propres
   jetons (faille historique de plusieurs bibliotheques) ;
2. la comparaison de signature passe par `hmac.compare_digest`, en temps
   constant, pour ne pas fuir la signature attendue octet par octet ;
3. le type de jeton (`typ`) est verifie : un jeton intermediaire de 2FA ne doit
   jamais etre accepte comme jeton d'acces.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from django.conf import settings

from core.http import ApiError

ALGORITHM = "HS256"

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_TWOFA = "twofa"


class InvalidToken(ApiError):
    def __init__(self, code: str = "invalid_token", message: str = "Jeton invalide.") -> None:
        super().__init__(code, message, 401)


def _b64url_encode(raw: bytes) -> str:
    """base64url sans remplissage, comme l'exige la RFC 7515."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError):
        raise InvalidToken() from None


def _sign(signing_input: bytes) -> bytes:
    secret = settings.JWT_SECRET.encode("utf-8")
    return hmac.new(secret, signing_input, hashlib.sha256).digest()


def encode(payload: dict[str, Any]) -> str:
    header = {"alg": ALGORITHM, "typ": "JWT"}
    segments = [
        _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode()),
        _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()),
    ]
    signing_input = ".".join(segments).encode("ascii")
    segments.append(_b64url_encode(_sign(signing_input)))
    return ".".join(segments)


def decode(token: str, *, expected_type: str) -> dict[str, Any]:
    """Verifie signature, expiration, emetteur et type. Leve InvalidToken sinon."""
    if not token or not isinstance(token, str):
        raise InvalidToken()

    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidToken()

    header_b64, payload_b64, signature_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    # L'algorithme attendu est celui du serveur. On lit quand meme l'en-tete
    # pour rejeter explicitement un jeton qui annoncerait autre chose.
    try:
        header = json.loads(_b64url_decode(header_b64))
    except (ValueError, UnicodeDecodeError):
        raise InvalidToken() from None
    if not isinstance(header, dict) or header.get("alg") != ALGORITHM:
        raise InvalidToken()

    if not hmac.compare_digest(_b64url_decode(signature_b64), _sign(signing_input)):
        raise InvalidToken()

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, UnicodeDecodeError):
        raise InvalidToken() from None
    if not isinstance(payload, dict):
        raise InvalidToken()

    if payload.get("iss") != settings.JWT_ISSUER:
        raise InvalidToken()

    if payload.get("typ") != expected_type:
        raise InvalidToken()

    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= int(time.time()):
        raise InvalidToken("token_expired", "Jeton expire.")

    return payload


def make_access_token(user_id: int, *, version: int = 0,
                      issued_at: int | None = None) -> tuple[str, int]:
    """Retourne (jeton, duree de vie en secondes).

    `version` recopie `User.token_version` : c'est ce que le middleware compare
    pour detecter un jeton revoque.
    """
    now = issued_at if issued_at is not None else int(time.time())
    ttl = settings.JWT_ACCESS_TTL
    payload = {
        "iss": settings.JWT_ISSUER,
        "sub": str(user_id),
        "typ": TOKEN_TYPE_ACCESS,
        "ver": version,
        "iat": now,
        "exp": now + ttl,
        # Identifiant unique : permet de tracer un jeton precis dans les logs
        # sans y ecrire le jeton lui-meme.
        "jti": secrets.token_urlsafe(8),
    }
    return encode(payload), ttl


def make_twofa_token(user_id: int) -> str:
    """Jeton intermediaire delivre apres le mot de passe, avant le code TOTP.

    Il ne donne acces a rien d'autre qu'a l'endpoint de verification du code :
    c'est ce qui permet de ne pas garder le mot de passe cote client entre les
    deux etapes.
    """
    now = int(time.time())
    payload = {
        "iss": settings.JWT_ISSUER,
        "sub": str(user_id),
        "typ": TOKEN_TYPE_TWOFA,
        "iat": now,
        "exp": now + settings.JWT_TWOFA_TTL,
        "jti": secrets.token_urlsafe(8),
    }
    return encode(payload)


def user_id_from_token(token: str, *, expected_type: str = TOKEN_TYPE_ACCESS) -> int:
    payload = decode(token, expected_type=expected_type)
    return subject_of(payload)


def subject_of(payload: dict[str, Any]) -> int:
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise InvalidToken() from None


def version_of(payload: dict[str, Any]) -> int:
    value = payload.get("ver")
    return value if isinstance(value, int) else -1
