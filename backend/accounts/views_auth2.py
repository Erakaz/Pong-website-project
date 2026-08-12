"""Double authentification (TOTP) et connexion 42."""

from __future__ import annotations

import re

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.utils import timezone

from accounts import jwt_utils, oauth42, tokens, totp
from accounts.models import BackupCode, User
from core.http import (ApiError, json_ok, login_required, read_json,
                       require_methods)
from core.validation import clean_text, field_str, validate_display_name

from accounts.views import _session_payload



@require_methods("POST")
@login_required
def twofa_setup(request):
    """Prepare l'activation : genere un secret, sans encore l'activer."""
    user = request.user
    if user.totp_enabled:
        raise ApiError("already_enabled", "La double authentification est deja active.", 409)

    secret = totp.generate_secret()
    user.totp_secret = secret
    user.save(update_fields=["totp_secret"])

    account = user.email or user.display_name
    return json_ok({
        "secret": secret,
        "otpauth_uri": totp.provisioning_uri(secret, account),
        "digits": totp.DIGITS,
        "period": totp.PERIOD,
    })


@require_methods("POST")
@login_required
def twofa_enable(request):
    data = read_json(request)
    user = request.user

    if user.totp_enabled:
        raise ApiError("already_enabled", "La double authentification est deja active.", 409)
    if not user.totp_secret:
        raise ApiError("setup_required", "Commence par generer un secret.", 409)

    code = field_str(data, "code", max_len=16)
    if not totp.verify(user.totp_secret, code):
        raise ApiError("invalid_code", "Code incorrect. Verifie l'heure de ton telephone.",
                       400, {"field": "code"})

    codes = totp.generate_backup_codes()
    with transaction.atomic():
        user.totp_enabled = True
        user.save(update_fields=["totp_enabled"])
        BackupCode.objects.filter(user=user).delete()
        BackupCode.objects.bulk_create(
            [BackupCode(user=user, code_hash=totp.hash_backup_code(code)) for code in codes],
        )
        user.revoke_all_tokens()

    response = json_ok({
        "user": user.private_dict(),
        "backup_codes": codes,
        **_session_payload(user),
    })
    return tokens.attach_session(response, tokens.issue(user))


@require_methods("POST")
@login_required
def twofa_disable(request):
    data = read_json(request)
    user = request.user

    if not user.totp_enabled:
        raise ApiError("not_enabled", "La double authentification n'est pas active.", 409)

    if user.has_usable_password():
        password = data.get("password")
        if not isinstance(password, str) or not user.check_password(password):
            raise ApiError("invalid_credentials", "Mot de passe incorrect.", 403,
                           {"field": "password"})
    else:
        code = field_str(data, "code", max_len=16)
        if not totp.verify(user.totp_secret, code):
            raise ApiError("invalid_code", "Code incorrect.", 400, {"field": "code"})

    with transaction.atomic():
        user.totp_enabled = False
        user.totp_secret = ""
        user.save(update_fields=["totp_enabled", "totp_secret"])
        BackupCode.objects.filter(user=user).delete()

    return json_ok({"user": user.private_dict()})


@require_methods("POST")
def twofa_verify(request):
    """Seconde etape de la connexion : le code a usage unique."""
    data = read_json(request)

    token = field_str(data, "twofa_token", max_len=2048, clean=False)
    try:
        user_id = jwt_utils.user_id_from_token(token,
                                               expected_type=jwt_utils.TOKEN_TYPE_TWOFA)
    except ApiError:
        raise ApiError("invalid_twofa_token",
                       "Etape expiree. Recommence la connexion.", 401) from None

    user = User.objects.filter(pk=user_id, is_active=True, totp_enabled=True).first()
    if user is None:
        raise ApiError("invalid_twofa_token", "Etape expiree. Recommence la connexion.", 401)

    code = field_str(data, "code", max_len=32)
    if not (totp.verify(user.totp_secret, code) or _consume_backup_code(user, code)):
        raise ApiError("invalid_code", "Code incorrect.", 400, {"field": "code"})

    user.last_seen = timezone.now()
    user.save(update_fields=["last_seen"])

    response = json_ok(_session_payload(user))
    return tokens.attach_session(response, tokens.issue(user))


def _consume_backup_code(user: User, code: str) -> bool:
    """Verifie et brule un code de secours. Chaque code ne sert qu'une fois."""
    digest = totp.hash_backup_code(code)
    with transaction.atomic():
        entry = (BackupCode.objects
                 .select_for_update()
                 .filter(user=user, code_hash=digest, used_at__isnull=True)
                 .first())
        if entry is None:
            return False
        entry.used_at = timezone.now()
        entry.save(update_fields=["used_at"])
    return True


@require_methods("GET")
@login_required
def twofa_status(request):
    remaining = BackupCode.objects.filter(user=request.user, used_at__isnull=True).count()
    return json_ok({"enabled": request.user.totp_enabled, "backup_codes_left": remaining})



def _state_cookie_kwargs() -> dict:
    return {
        "max_age": oauth42.STATE_TTL,
        "httponly": True,
        "secure": settings.SITE_ORIGIN.startswith("https://"),
        "samesite": "Lax",
        "path": "/api/auth",
    }


@require_methods("GET")
def oauth42_login(request):
    """Demarre le parcours : redirige le navigateur vers l'intra 42."""
    oauth42.ensure_enabled()

    state = oauth42.make_state()
    response = HttpResponseRedirect(oauth42.authorize_url(state))
    response.set_cookie(oauth42.STATE_COOKIE, state, **_state_cookie_kwargs())
    return response


@require_methods("POST")
@login_required
def oauth42_link_start(request):
    """Prepare la liaison d'un compte 42 a un compte existant."""
    oauth42.ensure_enabled()

    if request.user.oauth42_id:
        raise ApiError("already_linked", "Un compte 42 est deja lie.", 409)

    state = oauth42.make_state(f"link{request.user.pk}")
    response = json_ok({"authorize_url": oauth42.authorize_url(state)})
    response.set_cookie(oauth42.STATE_COOKIE, state, **_state_cookie_kwargs())
    return response


@require_methods("GET")
def oauth42_callback(request):
    """Retour de l'intra. Termine en redirigeant vers la SPA."""
    oauth42.ensure_enabled()

    expected = request.COOKIES.get(oauth42.STATE_COOKIE, "")
    received = request.GET.get("state", "")

    if request.GET.get("error"):
        return _finish("/login?oauth=denied")
    if not expected or not received or expected != received:
        return _finish("/login?oauth=state")

    code = request.GET.get("code", "")
    if not code or len(code) > 512:
        return _finish("/login?oauth=failed")

    try:
        profile = oauth42.fetch_profile(oauth42.exchange_code(code))
    except ApiError:
        return _finish("/login?oauth=failed")

    intent = oauth42.state_payload(received)
    try:
        if intent.startswith("link"):
            user = _link_profile(int(intent[4:]), profile)
        else:
            user = _login_or_create(profile)
    except ApiError as error:
        return _finish(f"/login?oauth={error.code}")

    user.last_seen = timezone.now()
    user.save(update_fields=["last_seen"])

    response = _finish("/?oauth=ok")
    response.delete_cookie(oauth42.STATE_COOKIE, path="/api/auth", samesite="Lax")
    return tokens.attach_session(response, tokens.issue(user))


def _finish(path: str) -> HttpResponseRedirect:
    return HttpResponseRedirect(f"{settings.SITE_ORIGIN}{path}")


@transaction.atomic
def _login_or_create(profile: dict) -> User:
    """Connecte le titulaire du compte 42, ou en cree un."""
    existing = User.objects.filter(oauth42_id=profile["id"]).first()
    if existing is not None:
        if not existing.is_active:
            raise ApiError("account_disabled", "Ce compte est desactive.", 403)
        if existing.oauth42_login != profile["login"]:
            existing.oauth42_login = profile["login"]
            existing.save(update_fields=["oauth42_login"])
        return existing

    if profile["email"] and User.objects.filter(email=profile["email"]).exists():
        raise ApiError("link_required",
                       "Un compte utilise deja cette adresse. Connecte-toi avec ton mot de "
                       "passe puis lie ton compte 42 depuis tes reglages.", 409)

    user = User.objects.create_user(
        email=profile["email"] or None,
        display_name=_available_display_name(profile["login"]),
        password=None,
        oauth42_id=profile["id"],
        oauth42_login=profile["login"],
    )
    return user


@transaction.atomic
def _link_profile(user_id: int, profile: dict) -> User:
    user = User.objects.select_for_update().filter(pk=user_id, is_active=True).first()
    if user is None:
        raise ApiError("not_found", "Compte introuvable.", 404)
    if user.oauth42_id:
        raise ApiError("already_linked", "Un compte 42 est deja lie.", 409)

    if User.objects.filter(oauth42_id=profile["id"]).exclude(pk=user.pk).exists():
        raise ApiError("already_used",
                       "Ce compte 42 est deja rattache a un autre profil.", 409)

    user.oauth42_id = profile["id"]
    user.oauth42_login = profile["login"]
    user.save(update_fields=["oauth42_id", "oauth42_login"])
    return user


def _available_display_name(login: str) -> str:
    """Derive un pseudo libre a partir du login 42."""
    base = re.sub(r"[^\w.\-]", "", clean_text(login)) or "joueur"
    base = base[:20]
    while len(base) < 3:
        base += "0"

    try:
        candidate = validate_display_name(base)
    except ApiError:
        candidate = "joueur"

    if not User.objects.filter(display_name=candidate).exists():
        return candidate

    for suffix in range(1, 1000):
        attempt = f"{candidate[:24 - len(str(suffix)) - 1]}-{suffix}"
        if not User.objects.filter(display_name=attempt).exists():
            return attempt

    raise ApiError("display_name_unavailable",
                   "Impossible de derive un pseudo disponible.", 409)
