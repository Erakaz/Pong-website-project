"""Middlewares transverses."""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404, HttpRequest, HttpResponse

from core import ratelimit
from core.http import ApiError, json_error

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """Applique un quota par IP sur les routes d'authentification."""

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
    """Convertit toute exception non geree en reponse JSON."""

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

        logger.exception("Exception non geree sur %s %s", request.method, request.path)
        return json_error("internal_error", "Erreur interne du serveur.", 500)
