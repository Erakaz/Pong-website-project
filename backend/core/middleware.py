"""Middlewares transverses."""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404, HttpRequest, HttpResponse

from core import ratelimit
from core.http import ApiError, json_error

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """Applique un quota par IP sur les routes d'authentification.

    Le quota porte sur les routes ou une tentative a un cout pour autrui :
    connexion, inscription, verification 2FA, rafraichissement. Le reste de
    l'API est deja protege par l'authentification.
    """

    # Prefixe d'URL -> nom du seau declare dans settings.RATE_LIMITS.
    BUCKETS = (
        ("/api/auth/login", "login"),
        ("/api/auth/register", "register"),
        ("/api/auth/2fa/verify", "twofa"),
        ("/api/auth/refresh", "refresh"),
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.method == "POST":
            for prefix, bucket in self.BUCKETS:
                if request.path == prefix:
                    allowed, window = ratelimit.hit(bucket, ratelimit.client_identity(request))
                    if not allowed:
                        logger.warning("Quota %s depasse pour %s", bucket,
                                       ratelimit.client_identity(request))
                        response = json_error(
                            "rate_limited",
                            "Trop de tentatives. Reessaie dans quelques minutes.", 429)
                        response["Retry-After"] = str(window)
                        return response
                    break
        return self.get_response(request)


class JsonErrorMiddleware:
    """Convertit toute exception non geree en reponse JSON.

    Sans lui, Django repondrait une page HTML d'erreur. La SPA parse chaque
    reponse de l'API en JSON : une page HTML declencherait une exception de
    parsing dans la console du navigateur, or le sujet exige qu'aucune erreur
    n'apparaisse en console.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_exception(self, request: HttpRequest, exception: Exception) -> HttpResponse | None:
        if isinstance(exception, ApiError):
            return exception.to_response()
        if isinstance(exception, Http404):
            return json_error("not_found", "Ressource introuvable.", 404)
        if isinstance(exception, PermissionDenied):
            return json_error("forbidden", "Acces refuse.", 403)
        if isinstance(exception, SuspiciousOperation):
            return json_error("bad_request", "Requete invalide.", 400)

        # Toute autre exception est un bug : elle est journalisee cote serveur
        # avec sa trace, mais le client ne recoit qu'un message generique — un
        # detail d'implementation renseignerait un attaquant.
        logger.exception("Exception non geree sur %s %s", request.method, request.path)
        return json_error("internal_error", "Erreur interne du serveur.", 500)
