"""Authentification par jeton porteur (Bearer) sur les requetes HTTP."""

from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse
from django.utils.functional import SimpleLazyObject

from accounts.authentication import resolve_token


def _resolve_user(request: HttpRequest):
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header:
        return AnonymousUser(), None

    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return AnonymousUser(), "invalid_token"

    user, error = resolve_token(token.strip())
    return (user or AnonymousUser()), error


class JWTAuthenticationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        resolved: dict = {}

        def load():
            if "user" not in resolved:
                user, error = _resolve_user(request)
                resolved["user"] = user
                request.auth_error = error
            return resolved["user"]

        request.auth_error = None
        request.user = SimpleLazyObject(load)
        return self.get_response(request)
