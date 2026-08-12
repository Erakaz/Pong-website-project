"""Resolution d'un access token en utilisateur.

Point unique partage par le middleware HTTP et par les consumers WebSocket :
sans cela, chaque canal reimplementerait ses propres verifications, et l'un
d'eux finirait par en oublier une (typiquement le controle de revocation).
"""

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
        # `token_expired` est distingue de `invalid_token` : le frontend
        # declenche un rafraichissement silencieux dans le premier cas, et une
        # deconnexion dans le second.
        return None, error.code

    try:
        user = User.objects.get(pk=jwt_utils.subject_of(payload))
    except (User.DoesNotExist, ApiError):
        return None, "invalid_token"

    if not user.is_active:
        return None, "account_disabled"

    # Revocation globale : le jeton porte la generation en cours au moment de
    # son emission. Toute incrementation cote compte le perime aussitot.
    if jwt_utils.version_of(payload) != user.token_version:
        return None, "token_revoked"

    return user, None
