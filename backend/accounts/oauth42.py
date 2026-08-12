"""Authentification distante via OAuth 2.0 avec l'intra 42."""

from __future__ import annotations

import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from core.http import ApiError

logger = logging.getLogger(__name__)

STATE_COOKIE = "ftt_oauth_state"
STATE_TTL = 600
HTTP_TIMEOUT = 10


def ensure_enabled() -> None:
    """Le module reste inerte tant que les credentials ne sont pas fournis."""
    if not settings.OAUTH42_ENABLED:
        raise ApiError(
            "oauth42_disabled",
            "La connexion 42 n'est pas configuree sur ce serveur.",
            503,
        )


def make_state(payload: str = "") -> str:
    """Valeur anti-rejeu, eventuellement porteuse d'une intention."""
    return f"{secrets.token_urlsafe(24)}:{payload}" if payload else secrets.token_urlsafe(24)


def state_payload(state: str) -> str:
    _, _, payload = state.partition(":")
    return payload


def authorize_url(state: str) -> str:
    params = {
        "client_id": settings.OAUTH42_UID,
        "redirect_uri": settings.OAUTH42_REDIRECT_URI,
        "response_type": "code",
        "scope": "public",
        "state": state,
    }
    return f"{settings.OAUTH42_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def _post_json(url: str, data: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode("utf-8"),
        headers={"Accept": "application/json",
                 "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        logger.warning("Echange de jeton 42 refuse (HTTP %s)", error.code)
        raise ApiError("oauth42_failed",
                       "L'intra 42 a refuse l'authentification.", 502) from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        logger.warning("Intra 42 injoignable ou reponse illisible")
        raise ApiError("oauth42_unreachable",
                       "L'intra 42 est injoignable. Reessaie plus tard.", 502) from None


def _get_json(url: str, access_token: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            json.JSONDecodeError):
        logger.warning("Lecture du profil 42 impossible")
        raise ApiError("oauth42_failed",
                       "Impossible de recuperer le profil 42.", 502) from None


def exchange_code(code: str) -> str:
    """Echange le code d'autorisation contre un jeton d'acces."""
    payload = _post_json(settings.OAUTH42_TOKEN_URL, {
        "grant_type": "authorization_code",
        "client_id": settings.OAUTH42_UID,
        "client_secret": settings.OAUTH42_SECRET,
        "code": code,
        "redirect_uri": settings.OAUTH42_REDIRECT_URI,
    })
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise ApiError("oauth42_failed", "Reponse inattendue de l'intra 42.", 502)
    return token


def fetch_profile(access_token: str) -> dict:
    """Profil 42 reduit aux champs dont l'application a besoin."""
    data = _get_json(settings.OAUTH42_ME_URL, access_token)

    identifier = data.get("id")
    login = data.get("login")
    if identifier is None or not login:
        raise ApiError("oauth42_failed", "Profil 42 incomplet.", 502)

    email = data.get("email") or ""
    return {
        "id": str(identifier),
        "login": str(login)[:64],
        "email": str(email).lower()[:254],
    }
