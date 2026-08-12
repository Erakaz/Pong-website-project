"""Socket de session : presence en ligne et notifications.

Une seule socket par onglet connecte, ouverte pendant toute la navigation. Elle
porte :

* la **presence** — tant qu'elle est ouverte, son proprietaire est « en ligne »,
  et ses amis en sont informes en temps reel (module « User management ») ;
* les **notifications** — invitations a jouer, annonce du prochain match de
  tournoi, messages directs (module « Live chat », branche a la phase suivante).

Le groupe `user.<id>` sert de boite aux lettres personnelle : n'importe quelle
partie du serveur peut y deposer un message pour cet utilisateur, quel que soit
l'onglet ou il se trouve.
"""

from __future__ import annotations

import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db.models import Q
from django.utils import timezone

from accounts.authentication import resolve_token
from accounts.models import Friendship, User
from core import presence
from core.http import ApiError

logger = logging.getLogger(__name__)

CLOSE_UNAUTHORIZED = 4001


def user_group(user_id: int) -> str:
    return f"user.{user_id}"


class LiveConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.user: User | None = None
        await self.accept()
        # Le client dispose d'un court instant pour s'authentifier ; sans quoi
        # il ne recevra jamais rien, faute d'appartenir a un groupe.

    async def disconnect(self, code: int) -> None:
        if self.user is None:
            return
        await self.channel_layer.group_discard(user_group(self.user.pk), self.channel_name)

        went_offline = presence.disconnect(self.user.pk)
        if went_offline:
            await _touch_last_seen(self.user.pk)
            await self._notify_friends(online=False)

    async def receive_json(self, content: dict, **kwargs) -> None:
        if not isinstance(content, dict):
            return

        kind = content.get("type")
        if kind == "auth":
            await self._handle_auth(content)
        elif kind == "ping":
            await self.send_json({"type": "pong"})
        elif self.user is None:
            await self.send_json({"type": "error", "code": "unauthorized"})
        elif kind == "chat":
            await self._handle_chat(content)

    async def _handle_chat(self, content: dict) -> None:
        """Message direct envoye en temps reel (module « Live chat »)."""
        recipient_id = content.get("to")
        body = content.get("body")
        if not isinstance(recipient_id, int) or not isinstance(body, str):
            return await self.send_json({"type": "error", "code": "invalid_message"})

        try:
            message = await _store_message(self.user, recipient_id, body)
        except ApiError as error:
            return await self.send_json({"type": "error", "code": error.code,
                                         "message": error.message})

        payload = {"type": "live.chat", "message": message}
        # Livre au destinataire, et renvoye a l'expediteur : ses autres onglets
        # doivent voir le message qu'il vient d'envoyer.
        await self.channel_layer.group_send(user_group(recipient_id), payload)
        await self.channel_layer.group_send(user_group(self.user.pk), payload)

    async def _handle_auth(self, content: dict) -> None:
        if self.user is not None:
            return

        user, error = await _resolve(content.get("token"))
        if user is None:
            await self.send_json({"type": "error", "code": error or "unauthorized"})
            return await self.close(code=CLOSE_UNAUTHORIZED)

        self.user = user

        await self.channel_layer.group_add(user_group(user.pk), self.channel_name)
        came_online = presence.connect(user.pk)
        await _touch_last_seen(user.pk)

        await self.send_json({
            "type": "ready",
            "user_id": user.pk,
            # L'etat initial des amis evite une requete HTTP supplementaire au
            # chargement de la liste d'amis.
            "online_friends": sorted(presence.filter_online(await _friend_ids(user))),
        })

        if came_online:
            await self._notify_friends(online=True)

    async def _notify_friends(self, *, online: bool) -> None:
        """Previent les amis d'un changement de statut.

        La liste d'amis est relue a chaque fois plutot que memorisee a la
        connexion : une amitie nouee pendant la session doit prendre effet
        immediatement, sans avoir a recharger la page.
        """
        for friend_id in await _friend_ids(self.user):
            await self.channel_layer.group_send(user_group(friend_id), {
                "type": "live.presence",
                "user_id": self.user.pk,
                "display_name": self.user.display_name,
                "online": online,
            })

    # -- Messages recus depuis le groupe personnel --------------------------

    async def live_presence(self, event: dict) -> None:
        await self.send_json({
            "type": "presence",
            "user_id": event["user_id"],
            "display_name": event["display_name"],
            "online": event["online"],
        })

    async def live_chat(self, event: dict) -> None:
        await self.send_json({"type": "chat", "message": event["message"]})

    async def live_notification(self, event: dict) -> None:
        """Notification generique (invitation, tour de tournoi, ...)."""
        payload = {key: value for key, value in event.items() if key != "type"}
        await self.send_json({"type": "notification", **payload})


# --- Acces base de donnees --------------------------------------------------

@database_sync_to_async
def _resolve(token) -> tuple[User | None, str | None]:
    return resolve_token(token)


@database_sync_to_async
def _store_message(sender: User, recipient_id: int, body: str) -> dict:
    from chat import services as chat_services

    recipient = User.objects.filter(pk=recipient_id, is_active=True).first()
    if recipient is None:
        raise ApiError("not_found", "Ce joueur n'existe pas.", 404)
    return chat_services.send_message(sender, recipient, body).to_dict()


@database_sync_to_async
def _friend_ids(user: User) -> list[int]:
    links = Friendship.objects.filter(
        Q(from_user=user) | Q(to_user=user), status=Friendship.ACCEPTED,
    ).values_list("from_user_id", "to_user_id")
    return [left if right == user.pk else right for left, right in links]


@database_sync_to_async
def _touch_last_seen(user_id: int) -> None:
    User.objects.filter(pk=user_id).update(last_seen=timezone.now())
