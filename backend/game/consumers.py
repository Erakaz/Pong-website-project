"""WebSocket de partie.

Protocole, cote client :

    {"type": "join",  "token": "<jwt ou null>"}
    {"type": "input", "side": 0, "dir": -1 | 0 | 1}
    {"type": "ping"}

Cote serveur :

    {"type": "joined",   "match": {...}, "geometry": {...}, "sides": [0, 1]}
    {"type": "state",    "state": {...}}          ~30 par seconde
    {"type": "events",   "events": [...]}         rebonds, points
    {"type": "opponent", "status": "left" | "back" | "forfeit", ...}
    {"type": "end",      "state": {...}, "match": {...}}
    {"type": "error",    "code": "...", "message": "..."}

Le client n'envoie qu'une intention de deplacement. Aucune position, aucune
vitesse, aucun score : tout cela est calcule et fait autorite cote serveur.
"""

from __future__ import annotations

import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from accounts.authentication import resolve_token
from accounts.models import User
from core.http import ApiError
from game import engine, rooms
from game.models import Match

logger = logging.getLogger(__name__)

# Fermetures applicatives : 4000+ est la plage reservee aux applications.
CLOSE_NOT_FOUND = 4004
CLOSE_SEAT_TAKEN = 4009
CLOSE_PROTOCOL = 4002


class MatchConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.match_id = self.scope["url_route"]["kwargs"]["match_id"]
        self.room: rooms.MatchRoom | None = None
        self.sides: set[int] = set()
        self.user = None
        # La socket est acceptee avant toute verification : c'est le message
        # `join` qui porte le jeton, jamais l'URL. Un jeton en query string se
        # retrouverait dans les journaux de nginx et l'historique du navigateur.
        await self.accept()

    async def disconnect(self, code: int) -> None:
        if self.room is None:
            return
        # On se contente de liberer la place : c'est la boucle de la partie qui
        # previendra l'adversaire, au meme instant ou elle met le jeu en pause.
        # Annoncer le depart d'ici arriverait avant la pause et laisserait un
        # bref intervalle ou le message et l'etat se contredisent.
        self.room.release(self.channel_name)
        await self.channel_layer.group_discard(self.room.group, self.channel_name)

    # -- Messages entrants --------------------------------------------------

    async def receive_json(self, content: dict, **kwargs) -> None:
        if not isinstance(content, dict):
            return await self._fail("bad_message", "Message illisible.")

        kind = content.get("type")
        if kind == "join":
            await self._handle_join(content)
        elif kind == "input":
            await self._handle_input(content)
        elif kind == "ping":
            await self.send_json({"type": "pong"})
        else:
            await self._fail("unknown_message", "Type de message inconnu.")

    async def _handle_join(self, content: dict) -> None:
        if self.room is not None:
            return await self._fail("already_joined", "Cette socket a deja rejoint la partie.")

        self.user = await self._authenticate(content.get("token"))

        match = await _load_match(self.match_id)
        if match is None:
            await self._fail("not_found", "Cette partie n'existe pas.")
            return await self.close(code=CLOSE_NOT_FOUND)

        if match.state in (Match.STATE_FINISHED, Match.STATE_ABORTED):
            # On renvoie quand meme le resultat : un lien partage vers une
            # partie terminee doit afficher le score, pas une erreur.
            await self.send_json({
                "type": "joined",
                "match": await _match_dict(match, self.user),
                "geometry": engine.geometry(),
                "sides": [],
                "replay": True,
            })
            return await self.close(code=1000)

        room = await rooms.registry.get_or_create(match)

        try:
            sides = self._sides_for(match, room)
        except ApiError as error:
            await self._fail(error.code, error.message)
            return await self.close(code=CLOSE_SEAT_TAKEN)

        self.room = room
        self.sides = sides
        await self.channel_layer.group_add(room.group, self.channel_name)
        returned = room.claim(self.channel_name, sides)

        await self.send_json({
            "type": "joined",
            "match": await _match_dict(match, self.user),
            "geometry": engine.geometry(),
            "sides": sorted(sides),
            "state": room.engine.snapshot(),
        })

        if returned:
            # La partie n'etait peut-etre pas encore gelee (retour tres rapide),
            # mais l'adversaire doit dans tous les cas voir disparaitre son
            # message d'attente.
            room.resume_if_ready()
            await self.channel_layer.group_send(
                room.group, {"type": "game.opponent", "status": "back",
                             "side": min(sides) if sides else None})

        # Le premier arrive attend son adversaire sans savoir qui viendra : on
        # previent tout le monde des qu'une place est prise, pour que l'ecran
        # d'attente affiche le nom du joueur en face.
        if sides and match.mode == Match.MODE_REMOTE:
            await self.channel_layer.group_send(room.group, {
                "type": "game.player",
                "match": await _match_dict(match, None),
            })

        if room.is_ready_to_start() and room.task is None:
            await room.start()

    def _sides_for(self, match: Match, room: rooms.MatchRoom) -> set[int]:
        """Determine les raquettes que cette socket a le droit de piloter."""
        if match.mode == Match.MODE_LOCAL:
            # Partie a deux sur un seul clavier : une unique socket pilote les
            # deux raquettes. Une seconde socket ne peut pas s'inviter.
            if room.occupied_sides:
                raise ApiError("seat_taken", "Quelqu'un joue deja cette partie.", 409)
            return {engine.LEFT, engine.RIGHT}

        side = match.side_of_user(self.user)
        if side is None:
            return set()          # spectateur : recoit l'etat, n'envoie rien
        if side in room.occupied_sides:
            raise ApiError("seat_taken", "Tu es deja connecte a cette partie ailleurs.", 409)
        return {side}

    async def _handle_input(self, content: dict) -> None:
        if self.room is None:
            return await self._fail("not_joined", "Il faut d'abord rejoindre la partie.")

        side = content.get("side")
        direction = content.get("dir")
        if side not in (engine.LEFT, engine.RIGHT) or direction not in (-1, 0, 1):
            return await self._fail("invalid_input", "Commande de deplacement invalide.")

        if not self.room.apply_input(self.channel_name, side, direction):
            # Tentative de bouger une raquette qui n'est pas la sienne.
            await self._fail("forbidden_side", "Cette raquette ne t'appartient pas.")

    async def _authenticate(self, token) -> User | None:
        """Un jeton absent ou invalide fait simplement un spectateur anonyme.

        On ne coupe pas la socket : une partie locale se joue sans compte, et
        un lien de match partage doit rester consultable.
        """
        if not token:
            return None
        user, _error = await _resolve(token)
        return user

    async def _fail(self, code: str, message: str) -> None:
        await self.send_json({"type": "error", "code": code, "message": message})

    # -- Messages diffuses par la salle -------------------------------------

    async def game_state(self, event: dict) -> None:
        await self.send_json({"type": "state", "state": event["state"]})

    async def game_events(self, event: dict) -> None:
        await self.send_json({"type": "events", "events": event["events"]})

    async def game_player(self, event: dict) -> None:
        await self.send_json({"type": "player", "match": event["match"]})

    async def game_opponent(self, event: dict) -> None:
        payload = {key: value for key, value in event.items() if key != "type"}
        await self.send_json({"type": "opponent", **payload})

    async def game_end(self, event: dict) -> None:
        await self.send_json({
            "type": "end",
            "state": event["state"],
            "stats": event.get("stats", {}),
            "match": event.get("match"),
        })

    async def game_aborted(self, event: dict) -> None:
        await self.send_json({"type": "aborted"})

    async def game_error(self, event: dict) -> None:
        await self.send_json({"type": "error", "code": event.get("code", "error"),
                              "message": "La partie a ete interrompue par une erreur serveur."})


# --- Acces base de donnees --------------------------------------------------

@database_sync_to_async
def _load_match(match_id) -> Match | None:
    try:
        return Match.objects.select_related("player1", "player2", "tournament").get(pk=match_id)
    except (Match.DoesNotExist, ValueError, TypeError):
        # ValueError couvre un UUID malforme dans l'URL.
        return None


@database_sync_to_async
def _resolve(token) -> tuple[User | None, str | None]:
    return resolve_token(token)


@database_sync_to_async
def _match_dict(match: Match, viewer) -> dict:
    return match.to_dict(viewer=viewer)
