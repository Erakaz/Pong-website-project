"""Authentification distante via OAuth 2.0 avec l'intra 42.

Flux « authorization code » classique, ecrit a la main avec `urllib` de la
bibliotheque standard : `django-allauth` resoudrait a lui seul tout le module,
ce que le sujet interdit.

Deroulement :

1. le navigateur part sur l'intra avec un parametre `state` imprevisible, dont
   une copie est deposee dans un cookie ephemere ;
2. l'intra renvoie sur notre callback avec un `code` et le meme `state` ;
3. le `state` recu est compare a celui du cookie. Sans ce controle, un tiers
   pourrait declencher la fin du flux avec SON code et lier son compte 42 au
   navigateur de la victime (« login CSRF ») ;
4. le `code` est echange contre un jeton d'acces, cote serveur uniquement, ce
   qui evite d'exposer le secret client.

Pas de PKCE ici, volontairement : PKCE protege les clients dits publics, ceux
qui ne peuvent pas garder de secret (applications mobiles, SPA sans backend).
Notre client est confidentiel — l'echange se fait de serveur a serveur avec
`OAUTH42_SECRET`, qui ne quitte jamais le conteneur.
"""

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
STATE_TTL = 600            # 10 minutes pour terminer le parcours
HTTP_TIMEOUT = 10          # secondes


def ensure_enabled() -> None:
    """Le module reste inerte tant que les credentials ne sont pas fournis."""
    if not settings.OAUTH42_ENABLED:
        raise ApiError(
            "oauth42_disabled",
            "La connexion 42 n'est pas configuree sur ce serveur.",
            503,
        )


def make_state(payload: str = "") -> str:
    """Valeur anti-rejeu, eventuellement porteuse d'une intention.

    Le format `alea:intention` permet de distinguer une simple connexion d'une
    liaison de compte, sans table temporaire cote serveur : l'integrite est
    assuree par la comparaison avec le cookie, que seul notre domaine peut
    poser.
    """
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
        # Le corps de la reponse d'erreur peut contenir le secret client
        # renvoye en echo : il n'est jamais journalise ni transmis au client.
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
        # L'identifiant numerique est l'ancre : un login 42 peut changer, pas lui.
        "id": str(identifier),
        "login": str(login)[:64],
        "email": str(email).lower()[:254],
    }
