"""Vues transverses : sonde de sante et gestionnaires d'erreur JSON."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from core.http import json_error, json_ok, require_methods


@require_methods("GET")
def health(request: HttpRequest) -> HttpResponse:
    """Sonde de vivacite utilisee par le healthcheck Docker du service backend."""
    return json_ok(
        {
            "status": "ok",
            "time": timezone.now().isoformat(),
            "features": {"oauth42": settings.OAUTH42_ENABLED},
        }
    )


def bad_request(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return json_error("bad_request", "Requete invalide.", 400)


def permission_denied(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return json_error("forbidden", "Acces refuse.", 403)


def not_found(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return json_error("not_found", "Ressource introuvable.", 404)


def server_error(request: HttpRequest) -> HttpResponse:
    return json_error("internal_error", "Erreur interne du serveur.", 500)
