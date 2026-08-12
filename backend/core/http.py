"""Briques communes des vues JSON."""

from __future__ import annotations

import functools
import json
from typing import Any, Callable, Iterable

from django.http import HttpRequest, HttpResponse, JsonResponse

MAX_JSON_BYTES = 64 * 1024


class ApiError(Exception):
    """Erreur applicative convertie en reponse JSON par JsonErrorMiddleware."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}

    def to_response(self) -> JsonResponse:
        return json_error(self.code, self.message, self.status, self.details)


def json_ok(data: Any = None, status: int = 200) -> JsonResponse:
    """Reponse de succes. `safe=False` autorise les listes a la racine."""
    return JsonResponse(data if data is not None else {}, status=status, safe=False)


def json_error(
    code: str,
    message: str,
    status: int = 400,
    details: dict[str, Any] | None = None,
) -> JsonResponse:
    """Forme d'erreur unique pour toute l'API."""
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return JsonResponse(payload, status=status)


def read_json(request: HttpRequest, *, max_bytes: int = MAX_JSON_BYTES) -> dict[str, Any]:
    """Decode le corps JSON d'une requete, ou leve une ApiError explicite."""
    body = request.body
    if len(body) > max_bytes:
        raise ApiError("payload_too_large", "Corps de requete trop volumineux.", 413)
    if not body:
        return {}
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ApiError("invalid_json", "Corps de requete JSON invalide.", 400) from None
    if not isinstance(data, dict):
        raise ApiError("invalid_json", "Le corps JSON doit etre un objet.", 400)
    return data


def require_methods(*methods: str) -> Callable:
    """Restreint une vue a une liste de verbes HTTP."""
    allowed = {m.upper() for m in methods}
    if "OPTIONS" not in allowed:
        allowed.add("OPTIONS")

    def decorator(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @functools.wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if request.method == "OPTIONS":
                response = HttpResponse(status=204)
                response["Allow"] = ", ".join(sorted(allowed))
                return response
            if request.method not in allowed:
                response = json_error(
                    "method_not_allowed",
                    f"Methode {request.method} non autorisee sur cette route.",
                    405,
                )
                response["Allow"] = ", ".join(sorted(allowed))
                return response
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def login_required(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """Refuse l'acces si JWTAuthenticationMiddleware n'a authentifie personne."""

    @functools.wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            code = getattr(request, "auth_error", None) or "unauthorized"
            message = ("Jeton expire." if code == "token_expired"
                       else "Authentification requise.")
            return json_error(code, message, 401)
        return view(request, *args, **kwargs)

    return wrapper


def paginate(queryset: Iterable, request: HttpRequest, *, default: int = 20,
             maximum: int = 100) -> tuple[list, dict[str, int]]:
    """Pagination par decalage, bornee pour eviter les requetes abusives."""
    try:
        limit = int(request.GET.get("limit", default))
    except (TypeError, ValueError):
        limit = default
    try:
        offset = int(request.GET.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0

    limit = max(1, min(limit, maximum))
    offset = max(0, offset)

    total = queryset.count() if hasattr(queryset, "count") else len(list(queryset))
    items = list(queryset[offset:offset + limit])
    return items, {"total": total, "limit": limit, "offset": offset}
