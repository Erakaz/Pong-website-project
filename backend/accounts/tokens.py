"""Jetons de rafraichissement et cookies d'authentification.

Modele de session retenu :

* **access token** — JWT court (15 min), transmis en en-tete `Authorization`,
  garde uniquement en memoire par le JavaScript. Jamais dans localStorage :
  une XSS y accederait instantanement ;
* **refresh token** — chaine aleatoire opaque, stockee cote client dans un
  cookie `httpOnly` que le JavaScript ne peut pas lire, et cote serveur sous
  forme de SHA-256 uniquement. Une fuite de la base ne permet donc pas de
  rejouer les sessions ;
* **rotation a usage unique** — chaque rafraichissement invalide l'ancien
  jeton et en emet un nouveau. Si un jeton deja consomme est represente, c'est
  qu'il a ete vole : toute la chaine de la session est alors revoquee.

Le cookie de refresh etant envoye automatiquement par le navigateur, l'endpoint
de rafraichissement serait vulnerable au CSRF. Deux protections se cumulent :
`SameSite=Strict`, et une double soumission (un cookie non-httpOnly renvoye en
en-tete `X-CSRF-Token`, qu'un site tiers ne peut pas lire donc pas reproduire).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from accounts.models import RefreshToken, User
from core.http import ApiError

REFRESH_BYTES = 48
REFRESH_PATH = "/api/auth"


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cookies_secure() -> bool:
    # En production le site est en HTTPS et le cookie doit etre `Secure`. En
    # developpement local en clair, un cookie `Secure` ne serait jamais pose et
    # la connexion paraitrait cassee sans raison visible.
    return settings.SITE_ORIGIN.startswith("https://")


def issue(user: User) -> str:
    """Cree un nouveau jeton de rafraichissement et retourne sa valeur claire."""
    raw = secrets.token_urlsafe(REFRESH_BYTES)
    RefreshToken.objects.create(
        user=user,
        token_hash=_hash(raw),
        expires_at=timezone.now() + timedelta(seconds=settings.JWT_REFRESH_TTL),
    )
    return raw


def rotate(raw: str) -> tuple[str, User]:
    """Echange un jeton contre un nouveau. Detecte et neutralise les rejeux."""
    stored = (RefreshToken.objects
              .select_related("user")
              .filter(token_hash=_hash(raw))
              .first())
    if stored is None:
        raise ApiError("invalid_refresh", "Session inconnue ou expiree.", 401)

    if stored.rotated_to_id is not None:
        # Ce jeton a deja servi. Soit un attaquant rejoue un jeton vole, soit
        # le veritable proprietaire utilise une copie perimee : dans les deux
        # cas on coupe tout, l'utilisateur se reconnecte.
        stored.user.revoke_all_tokens()
        raise ApiError("refresh_reused",
                       "Session invalidee pour raison de securite. Reconnecte-toi.", 401)

    if not stored.is_valid():
        raise ApiError("invalid_refresh", "Session expiree.", 401)
    if not stored.user.is_active:
        raise ApiError("account_disabled", "Ce compte est desactive.", 403)

    raw_next = secrets.token_urlsafe(REFRESH_BYTES)
    replacement = RefreshToken.objects.create(
        user=stored.user,
        token_hash=_hash(raw_next),
        expires_at=timezone.now() + timedelta(seconds=settings.JWT_REFRESH_TTL),
    )
    stored.rotated_to = replacement
    stored.revoked_at = timezone.now()
    stored.save(update_fields=["rotated_to", "revoked_at"])

    return raw_next, stored.user


def revoke(raw: str) -> None:
    """Invalide un jeton a la deconnexion. Silencieux s'il n'existe pas."""
    RefreshToken.objects.filter(token_hash=_hash(raw), revoked_at__isnull=True).update(
        revoked_at=timezone.now(),
    )


def purge_expired() -> int:
    """Supprime les jetons perimes. Appele a chaque connexion, sans tache de fond."""
    deleted, _ = RefreshToken.objects.filter(
        expires_at__lt=timezone.now() - timedelta(days=1),
    ).delete()
    return deleted


# --- Cookies ---------------------------------------------------------------

def read_refresh_cookie(request: HttpRequest) -> str:
    raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME, "")
    if not raw:
        raise ApiError("no_session", "Aucune session en cours.", 401)
    return raw


def verify_csrf(request: HttpRequest) -> None:
    """Double soumission : le cookie doit egaler l'en-tete.

    Un site tiers peut declencher la requete (le navigateur joindra le cookie),
    mais il ne peut pas lire le cookie pour reconstituer l'en-tete : la
    politique d'origine du navigateur l'en empeche.
    """
    cookie = request.COOKIES.get(settings.CSRF_COOKIE_NAME, "")
    header = request.headers.get(settings.CSRF_HEADER_NAME, "")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise ApiError("csrf_failed", "Verification anti-CSRF echouee.", 403)


def attach_session(response: HttpResponse, raw_refresh: str) -> HttpResponse:
    secure = _cookies_secure()

    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        raw_refresh,
        max_age=settings.JWT_REFRESH_TTL,
        httponly=True,          # invisible du JavaScript, donc hors de portee d'une XSS
        secure=secure,
        samesite="Strict",      # jamais envoye depuis un autre site
        path=REFRESH_PATH,      # seules les routes d'auth le recoivent
    )
    # Temoin lisible par le JS : sert au jeton anti-CSRF et evite d'appeler
    # l'endpoint de rafraichissement quand aucune session n'existe.
    response.set_cookie(
        settings.CSRF_COOKIE_NAME,
        secrets.token_urlsafe(24),
        max_age=settings.JWT_REFRESH_TTL,
        httponly=False,
        secure=secure,
        samesite="Strict",
        path="/",
    )
    return response


def clear_session(response: HttpResponse) -> HttpResponse:
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path=REFRESH_PATH,
                           samesite="Strict")
    response.delete_cookie(settings.CSRF_COOKIE_NAME, path="/", samesite="Strict")
    return response
