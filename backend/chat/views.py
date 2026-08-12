"""API de la messagerie : historique, blocages, invitations.

L'envoi en temps reel passe par le socket de session (`ws/live`) ; ces routes
servent au chargement initial et aux actions ponctuelles.
"""

from __future__ import annotations

from accounts.models import User
from chat import services
from chat.models import Message
from core.http import (ApiError, json_ok, login_required, read_json,
                       require_methods)
from core.validation import field_bool, field_str
from game import services as game_services
from game.models import Match


def _get_user(user_id: int) -> User:
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        raise ApiError("not_found", "Ce joueur n'existe pas.", 404)
    return user


@require_methods("GET")
@login_required
def conversations(request):
    return json_ok({
        "conversations": services.conversations(request.user),
        "blocked": services.blocked_ids(request.user),
        "unread": services.unread_count(request.user),
    })


@require_methods("GET", "POST")
@login_required
def conversation(request, user_id):
    other = _get_user(user_id)

    if request.method == "POST":
        data = read_json(request)
        body = field_str(data, "body", max_len=services.MESSAGE_MAX_LENGTH)
        message = services.send_message(request.user, other, body)
        _deliver(message)
        return json_ok({"message": message.to_dict()}, status=201)

    services.mark_read(request.user, other)
    return json_ok({
        "user": other.public_dict(),
        "messages": [message.to_dict()
                     for message in services.conversation(request.user, other)],
        "blocked": other.pk in services.blocked_ids(request.user),
    })


@require_methods("POST")
@login_required
def block(request, user_id):
    other = _get_user(user_id)
    data = read_json(request)
    services.set_block(request.user, other, field_bool(data, "blocked", default=True))
    return json_ok({"blocked": services.blocked_ids(request.user)})


@require_methods("POST")
@login_required
def invite(request, user_id):
    """Invite quelqu'un a jouer, depuis la conversation.

    La partie est creee tout de suite : l'invitation porte un lien direct, et
    l'invite n'a rien a chercher dans le salon.
    """
    other = _get_user(user_id)
    if services.is_blocked(request.user, other):
        raise ApiError("not_delivered", "Cette invitation n'a pas pu etre envoyee.", 403)

    match = game_services.create_remote_match(user=request.user, points_to_win=5)
    match.player2 = other
    match.save(update_fields=["player2"])

    message = services.send_message(
        request.user, other,
        f"{request.user.display_name} t'invite a jouer.",
        kind=Message.KIND_INVITE, match=match,
    )
    _deliver(message)
    return json_ok({"message": message.to_dict(),
                    "match": match.to_dict(viewer=request.user)}, status=201)


def _deliver(message: Message) -> None:
    """Pousse le message dans les boites aux lettres temps reel concernees.

    Les DEUX cotes sont servis, pas seulement le destinataire : l'expediteur
    peut avoir plusieurs onglets ouverts, et celui d'ou part le message doit
    l'afficher comme les autres. C'est aussi le comportement du chemin
    WebSocket, les deux restent ainsi interchangeables.
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    from accounts.consumers import user_group

    layer = get_channel_layer()
    if layer is None:
        return

    payload = {"type": "live.chat", "message": message.to_dict()}
    for user_id in {message.sender_id, message.recipient_id}:
        if user_id is not None:
            async_to_sync(layer.group_send)(user_group(user_id), payload)


@require_methods("GET")
@login_required
def invitation_match(request, match_id):
    """Detail d'une partie recue en invitation, pour l'afficher dans le fil."""
    match = Match.objects.filter(pk=match_id).first()
    if match is None:
        raise ApiError("not_found", "Cette partie n'existe plus.", 404)
    return json_ok({"match": match.to_dict(viewer=request.user)})
