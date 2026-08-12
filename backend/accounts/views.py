"""Comptes : inscription, connexion, profil, amis.

Module « Standard user management, authentication, users across tournaments ».

Toutes les routes de modification portent `@login_required` : le sujet insiste
(« ensure your routes are protected »). Les routes de lecture publique se
limitent a ce qu'un joueur accepte d'exposer — pseudo, avatar, statistiques —
et jamais l'adresse e-mail.
"""

from __future__ import annotations

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from accounts import jwt_utils, tokens
from accounts.avatars import process as process_avatar
from accounts.models import Friendship, User
from core import presence
from core.http import (ApiError, json_ok, login_required, paginate, read_json,
                       require_methods)
from core.validation import (field_str, validate_display_name, validate_email,
                             validate_password)
from game import stats


# ---------------------------------------------------------------------------
#  Authentification
# ---------------------------------------------------------------------------

def _session_payload(user: User) -> dict:
    access_token, expires_in = jwt_utils.make_access_token(user.pk,
                                                           version=user.token_version)
    return {
        "access_token": access_token,
        "expires_in": expires_in,
        "user": user.private_dict(),
    }


@require_methods("POST")
def register(request):
    data = read_json(request)
    email = validate_email(field_str(data, "email", max_len=254))
    display_name = validate_display_name(field_str(data, "display_name", max_len=64))

    # Un utilisateur provisoire sert de contexte aux validateurs Django, qui
    # refusent un mot de passe trop proche du pseudo ou de l'e-mail.
    candidate = User(email=email, display_name=display_name)
    password = validate_password(data.get("password"), candidate)

    try:
        with transaction.atomic():
            user = User.objects.create_user(email=email, display_name=display_name,
                                            password=password)
    except IntegrityError:
        # Le doublon est detecte par la contrainte d'unicite de PostgreSQL, pas
        # par un `exists()` prealable : entre les deux, deux inscriptions
        # simultanees passeraient toutes les deux.
        raise ApiError("account_exists",
                       "Un compte existe deja avec cet e-mail ou ce pseudo.", 409) from None

    payload = _session_payload(user)
    response = json_ok(payload, status=201)
    return tokens.attach_session(response, tokens.issue(user))


@require_methods("POST")
def login(request):
    data = read_json(request)
    email = field_str(data, "email", max_len=254).lower()
    password = data.get("password")

    user = User.objects.filter(email=email).first()

    # Le hachage est calcule meme quand le compte n'existe pas : sans cela, le
    # temps de reponse revelerait quelles adresses sont inscrites.
    if user is None:
        User().set_password(password if isinstance(password, str) else "")
        raise ApiError("invalid_credentials", "E-mail ou mot de passe incorrect.", 401)

    if not isinstance(password, str) or not user.check_password(password):
        raise ApiError("invalid_credentials", "E-mail ou mot de passe incorrect.", 401)
    if not user.is_active:
        raise ApiError("account_disabled", "Ce compte a ete desactive.", 403)

    tokens.purge_expired()

    # Le module 2FA intercepte ici : avec la double authentification active, le
    # mot de passe ne donne qu'un jeton intermediaire, pas la session.
    if user.totp_enabled:
        return json_ok({
            "twofa_required": True,
            "twofa_token": jwt_utils.make_twofa_token(user.pk),
        })

    user.last_seen = timezone.now()
    user.save(update_fields=["last_seen"])

    response = json_ok(_session_payload(user))
    return tokens.attach_session(response, tokens.issue(user))


@require_methods("POST")
def refresh(request):
    tokens.verify_csrf(request)
    raw = tokens.read_refresh_cookie(request)
    try:
        raw_next, user = tokens.rotate(raw)
    except ApiError:
        # Session morte : on efface les cookies pour que le prochain
        # chargement de page n'appelle plus cette route.
        response = json_ok({"error": "session_expired"}, status=401)
        return tokens.clear_session(response)

    response = json_ok(_session_payload(user))
    return tokens.attach_session(response, raw_next)


@require_methods("POST")
def logout(request):
    raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME, "")
    if raw:
        tokens.revoke(raw)
    return tokens.clear_session(json_ok({"ok": True}))


@require_methods("POST")
@login_required
def logout_all(request):
    """Deconnecte toutes les sessions du compte, y compris celle-ci."""
    request.user.revoke_all_tokens()
    return tokens.clear_session(json_ok({"ok": True}))


# ---------------------------------------------------------------------------
#  Compte courant
# ---------------------------------------------------------------------------

@require_methods("GET", "PATCH")
@login_required
def me(request):
    if request.method == "PATCH":
        return _update_me(request)
    return json_ok({"user": request.user.private_dict()})


def _update_me(request):
    data = read_json(request)
    user = request.user
    changed = []

    if "display_name" in data:
        user.display_name = validate_display_name(field_str(data, "display_name", max_len=64))
        changed.append("display_name")

    if "language" in data:
        language = field_str(data, "language", max_len=5)
        if language not in {"fr", "en"}:
            raise ApiError("invalid_field", "Langue non prise en charge.", 400,
                           {"field": "language"})
        user.language = language
        changed.append("language")

    if "email" in data:
        user.email = validate_email(field_str(data, "email", max_len=254))
        changed.append("email")

    if not changed:
        return json_ok({"user": user.private_dict()})

    try:
        user.save(update_fields=changed)
    except IntegrityError:
        raise ApiError("already_taken", "Ce pseudo ou cet e-mail est deja utilise.", 409,
                       {"field": "display_name"}) from None
    return json_ok({"user": user.private_dict()})


@require_methods("POST")
@login_required
def change_password(request):
    data = read_json(request)
    user = request.user

    # Un compte cree via 42 n'a pas de mot de passe : il peut en definir un
    # sans avoir a prouver l'ancien, qui n'existe pas.
    if user.has_usable_password():
        current = data.get("current_password")
        if not isinstance(current, str) or not user.check_password(current):
            raise ApiError("invalid_credentials", "Mot de passe actuel incorrect.", 403,
                           {"field": "current_password"})

    new_password = validate_password(data.get("password"), user)
    user.set_password(new_password)
    user.save(update_fields=["password"])

    # Changer de mot de passe doit fermer les sessions ouvertes ailleurs :
    # c'est le geste attendu apres un soupcon de compromission.
    user.revoke_all_tokens()

    response = json_ok(_session_payload(user))
    return tokens.attach_session(response, tokens.issue(user))


@require_methods("POST", "DELETE")
@login_required
def avatar(request):
    user = request.user

    if request.method == "DELETE":
        if user.avatar:
            user.avatar.delete(save=False)
        user.avatar = None
        user.save(update_fields=["avatar"])
        return json_ok({"user": user.private_dict()})

    uploaded = request.FILES.get("avatar")
    processed = process_avatar(uploaded)

    if user.avatar:
        # L'ancien fichier est supprime du disque : sans cela, chaque
        # changement d'avatar laisserait un orphelin sur le volume.
        user.avatar.delete(save=False)
    user.avatar.save("avatar.png", processed, save=True)
    return json_ok({"user": user.private_dict()})


@require_methods("GET")
@login_required
def my_matches(request):
    return json_ok({
        "stats": stats.summary(request.user),
        "history": stats.history(request.user, limit=50),
    })


# ---------------------------------------------------------------------------
#  Autres joueurs
# ---------------------------------------------------------------------------

@require_methods("GET")
@login_required
def users(request):
    """Recherche de joueurs, pour ajouter un ami ou ouvrir une conversation."""
    query = field_str(request.GET, "q", required=False, max_len=24)
    queryset = User.objects.filter(is_active=True, is_anonymized=False).exclude(pk=request.user.pk)
    if query:
        queryset = queryset.filter(display_name__icontains=query)
    queryset = queryset.order_by("display_name")

    items, meta = paginate(queryset, request, default=10, maximum=25)
    return json_ok({
        "users": [{**user.public_dict(), "online": presence.is_online(user.pk)}
                  for user in items],
        "meta": meta,
    })


@require_methods("GET")
@login_required
def user_detail(request, user_id):
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        raise ApiError("not_found", "Ce joueur n'existe pas.", 404)

    return json_ok({
        "user": {
            **user.public_dict(),
            "online": presence.is_online(user.pk),
            "last_seen": user.last_seen.isoformat() if user.last_seen else None,
            "date_joined": user.date_joined.isoformat(),
        },
        "stats": stats.summary(user),
        "history": stats.history(user, limit=20),
        "friendship": _friendship_state(request.user, user),
    })


# ---------------------------------------------------------------------------
#  Amis
# ---------------------------------------------------------------------------

def _friendship_between(a: User, b: User) -> Friendship | None:
    return Friendship.objects.filter(
        Q(from_user=a, to_user=b) | Q(from_user=b, to_user=a),
    ).first()


def _friendship_state(viewer: User, other: User) -> dict:
    if viewer.pk == other.pk:
        return {"status": "self"}
    link = _friendship_between(viewer, other)
    if link is None:
        return {"status": "none"}
    if link.status == Friendship.ACCEPTED:
        return {"status": "friends", "id": link.pk}
    direction = "outgoing" if link.from_user_id == viewer.pk else "incoming"
    return {"status": "pending", "direction": direction, "id": link.pk}


@require_methods("GET", "POST")
@login_required
def friends(request):
    if request.method == "POST":
        return _add_friend(request)

    links = (Friendship.objects
             .filter(Q(from_user=request.user) | Q(to_user=request.user))
             .select_related("from_user", "to_user"))

    accepted, incoming, outgoing = [], [], []
    for link in links:
        other = link.other(request.user)
        entry = {
            "id": link.pk,
            "user": {**other.public_dict(), "online": presence.is_online(other.pk),
                     "last_seen": other.last_seen.isoformat() if other.last_seen else None},
        }
        if link.status == Friendship.ACCEPTED:
            accepted.append(entry)
        elif link.to_user_id == request.user.pk:
            incoming.append(entry)
        else:
            outgoing.append(entry)

    accepted.sort(key=lambda entry: (not entry["user"]["online"],
                                     entry["user"]["display_name"].casefold()))
    return json_ok({"friends": accepted, "incoming": incoming, "outgoing": outgoing})


def _add_friend(request):
    data = read_json(request)
    display_name = validate_display_name(field_str(data, "display_name", max_len=64))

    target = User.objects.filter(display_name=display_name, is_active=True,
                                 is_anonymized=False).first()
    if target is None:
        raise ApiError("not_found", "Aucun joueur ne porte ce pseudo.", 404,
                       {"field": "display_name"})
    if target.pk == request.user.pk:
        raise ApiError("invalid_target", "Tu ne peux pas t'ajouter toi-meme.", 400,
                       {"field": "display_name"})

    existing = _friendship_between(request.user, target)
    if existing is not None:
        if existing.status == Friendship.ACCEPTED:
            raise ApiError("already_friends", "Vous etes deja amis.", 409)
        if existing.to_user_id == request.user.pk:
            # Demande croisee : les deux se sont ajoutes, on valide directement.
            existing.status = Friendship.ACCEPTED
            existing.accepted_at = timezone.now()
            existing.save(update_fields=["status", "accepted_at"])
            return json_ok({"friendship": _friendship_state(request.user, target)})
        raise ApiError("already_requested", "Demande deja envoyee.", 409)

    Friendship.objects.create(from_user=request.user, to_user=target)
    return json_ok({"friendship": _friendship_state(request.user, target)}, status=201)


@require_methods("POST")
@login_required
def friend_accept(request, friendship_id):
    link = Friendship.objects.filter(pk=friendship_id, to_user=request.user,
                                     status=Friendship.PENDING).first()
    if link is None:
        raise ApiError("not_found", "Cette demande n'existe pas.", 404)
    link.status = Friendship.ACCEPTED
    link.accepted_at = timezone.now()
    link.save(update_fields=["status", "accepted_at"])
    return json_ok({"friendship": _friendship_state(request.user, link.other(request.user))})


@require_methods("DELETE")
@login_required
def friend_remove(request, friendship_id):
    """Sert au refus d'une demande comme a la suppression d'un ami."""
    deleted, _ = Friendship.objects.filter(
        Q(from_user=request.user) | Q(to_user=request.user), pk=friendship_id,
    ).delete()
    if not deleted:
        raise ApiError("not_found", "Cette relation n'existe pas.", 404)
    return json_ok({"ok": True})
