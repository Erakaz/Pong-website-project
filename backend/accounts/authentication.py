"""Resolution d'un access token en utilisateur."""

from __future__ import annotations

from accounts import jwt_utils
from accounts.models import User
from core.http import ApiError


def resolve_token(token: str) -> tuple[User | None, str | None]:
    """Retourne (utilisateur, code d'erreur). L'un des deux vaut toujours None."""
    if not token or not isinstance(token, str):
        return None, "unauthorized"

    try:
        payload = jwt_utils.decode(token, expected_type=jwt_utils.TOKEN_TYPE_ACCESS)
    except ApiError as error:
        return None, error.code

    try:
        user = User.objects.get(pk=jwt_utils.subject_of(payload))
    except (User.DoesNotExist, ApiError):
        return None, "invalid_token"

    if not user.is_active:
        return None, "account_disabled"

    if jwt_utils.version_of(payload) != user.token_version:
        return None, "token_revoked"

    return user, None
