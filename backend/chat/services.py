"""Regles metier de la messagerie.

Regroupees ici parce qu'elles sont appelees depuis deux endroits : les vues
HTTP (historique, blocages) et le socket de session (envoi temps reel). Le
controle de blocage en particulier ne doit exister qu'a un seul endroit.
"""

from __future__ import annotations

from django.db.models import Max, Q

from accounts.models import User
from chat.models import Block, Message
from core.http import ApiError
from core.validation import clean_text

MESSAGE_MAX_LENGTH = 1000


def is_blocked(sender: User, recipient: User) -> bool:
    """Vrai si l'un des deux a bloque l'autre.

    Le blocage coupe la conversation dans les DEUX sens : laisser la personne
    bloquee continuer a recevoir les messages de celle qui l'a bloquee serait
    incoherent, et permettrait de deviner qu'on a ete bloque.
    """
    return Block.objects.filter(
        Q(blocker=sender, blocked=recipient) | Q(blocker=recipient, blocked=sender),
    ).exists()


def send_message(sender: User, recipient: User, body: str, *,
                 kind: str = Message.KIND_TEXT, match=None) -> Message:
    if recipient.pk == sender.pk:
        raise ApiError("invalid_recipient", "Impossible de s'ecrire a soi-meme.", 400)
    if not recipient.is_active or recipient.is_anonymized:
        raise ApiError("not_found", "Ce joueur n'est plus joignable.", 404)
    if is_blocked(sender, recipient):
        # Message volontairement neutre : reveler « tu es bloque » donnerait a
        # un harceleur l'information qu'il cherche.
        raise ApiError("not_delivered", "Ce message n'a pas pu etre delivre.", 403)

    text = clean_text(body)
    if kind == Message.KIND_TEXT and not text:
        raise ApiError("empty_message", "Un message ne peut pas etre vide.", 400,
                       {"field": "body"})
    if len(text) > MESSAGE_MAX_LENGTH:
        raise ApiError("message_too_long",
                       f"Un message ne peut pas depasser {MESSAGE_MAX_LENGTH} caracteres.",
                       400, {"field": "body"})

    return Message.objects.create(sender=sender, recipient=recipient, body=text,
                                  kind=kind, match=match)


def notify(recipient: User, body: str, *, match=None) -> Message:
    """Message du systeme (annonce de tournoi). Aucun expediteur humain."""
    return Message.objects.create(sender=None, recipient=recipient, body=body,
                                  kind=Message.KIND_SYSTEM, match=match)


def conversation(user: User, other: User, *, limit: int = 50) -> list[Message]:
    """Fil entre deux personnes, du plus ancien au plus recent."""
    # `id` departage deux messages du meme instant : sans lui, l'ordre de deux
    # messages ecrits dans la meme microseconde serait laisse au hasard du
    # moteur de base de donnees.
    queryset = (Message.objects
                .filter(Q(sender=user, recipient=other) | Q(sender=other, recipient=user))
                .order_by("-created_at", "-id")[:limit])
    return list(reversed(list(queryset)))


def conversations(user: User) -> list[dict]:
    """Liste des fils, tries par activite la plus recente.

    Les personnes bloquees en sont exclues : leur conversation ne doit plus
    apparaitre du tout.
    """
    blocked_ids = set(Block.objects.filter(Q(blocker=user) | Q(blocked=user))
                      .values_list("blocker_id", "blocked_id"))
    excluded = {pk for pair in blocked_ids for pk in pair} - {user.pk}

    messages = (Message.objects
                .filter(Q(sender=user) | Q(recipient=user))
                .exclude(sender_id__in=excluded)
                .exclude(recipient_id__in=excluded)
                .values("sender_id", "recipient_id")
                .annotate(last=Max("created_at")))

    latest: dict[int, str] = {}
    for row in messages:
        other_id = row["recipient_id"] if row["sender_id"] == user.pk else row["sender_id"]
        if other_id is None or other_id == user.pk:
            continue                      # message systeme, sans interlocuteur
        current = latest.get(other_id)
        if current is None or row["last"] > current:
            latest[other_id] = row["last"]

    if not latest:
        return []

    unread = dict(Message.objects
                  .filter(recipient=user, read_at__isnull=True, sender_id__in=latest)
                  .values_list("sender_id")
                  .annotate(total=Max("created_at"))
                  .values_list("sender_id", "total"))

    others = {user.pk: user for user in User.objects.filter(pk__in=latest)}
    entries = []
    for other_id, last in latest.items():
        other = others.get(other_id)
        if other is None:
            continue
        entries.append({
            "user": other.public_dict(),
            "last_at": last.isoformat(),
            "unread": other_id in unread,
        })
    entries.sort(key=lambda entry: entry["last_at"], reverse=True)
    return entries


def mark_read(user: User, other: User) -> int:
    from django.utils import timezone

    return Message.objects.filter(recipient=user, sender=other,
                                  read_at__isnull=True).update(read_at=timezone.now())


def unread_count(user: User) -> int:
    return Message.objects.filter(recipient=user, read_at__isnull=True).count()


def set_block(blocker: User, target: User, blocked: bool) -> None:
    if blocker.pk == target.pk:
        raise ApiError("invalid_target", "Impossible de se bloquer soi-meme.", 400)
    if blocked:
        Block.objects.get_or_create(blocker=blocker, blocked=target)
    else:
        Block.objects.filter(blocker=blocker, blocked=target).delete()


def blocked_ids(user: User) -> list[int]:
    return list(Block.objects.filter(blocker=user).values_list("blocked_id", flat=True))
