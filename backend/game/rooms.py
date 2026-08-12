"""Salles de jeu : la boucle temps reel qui fait tourner le moteur."""

from __future__ import annotations

import asyncio
import logging
import time

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer

from game import engine, services
from game.engine import PongEngine

logger = logging.getLogger(__name__)

DISCONNECT_GRACE = 20.0

EMPTY_ROOM_TIMEOUT = 120.0

SNAPSHOT_EVERY = 2


def group_name(match_id) -> str:
    return f"match.{match_id}"


class MatchRoom:
    """Etat vivant d'une partie."""

    def __init__(self, match_id: str, *, mode: str, points_to_win: int, seed: int):
        self.match_id = str(match_id)
        self.mode = mode
        self.group = group_name(match_id)
        self.engine = PongEngine(points_to_win=points_to_win, seed=seed)

        self.channels: dict[str, set[int]] = {}
        self.disconnected_since: dict[int, float] = {}

        self.task: asyncio.Task | None = None
        self.started = False
        self.finished = False
        self.created_at = time.monotonic()
        self.empty_since: float | None = None
        self.points_log: list[dict] = []
        self._layer = get_channel_layer()
        self._lock = asyncio.Lock()


    @property
    def occupied_sides(self) -> set[int]:
        return {side for sides in self.channels.values() for side in sides}

    def claim(self, channel_name: str, sides: set[int]) -> bool:
        """Enregistre une socket. Retourne True s'il s'agit d'un RETOUR."""
        self.channels[channel_name] = set(sides)
        return any(self.disconnected_since.pop(side, None) is not None for side in sides)

    def release(self, channel_name: str) -> set[int]:
        """Retire une socket. Retourne les cotes qu'elle controlait."""
        sides = self.channels.pop(channel_name, set())
        now = time.monotonic()
        for side in sides:
            self.disconnected_since[side] = now
        return sides

    def is_ready_to_start(self) -> bool:
        """La partie demarre quand les deux raquettes ont un pilote."""
        return self.occupied_sides == {engine.LEFT, engine.RIGHT}

    def resume_if_ready(self) -> bool:
        """Relance une partie mise en pause quand tout le monde est revenu."""
        if self.disconnected_since or not self.is_ready_to_start():
            return False
        if self.engine.status != engine.STATUS_PAUSED:
            return False
        self.engine.resume()
        return True


    def apply_input(self, channel_name: str, side: int, direction: int) -> bool:
        """Applique un input si la socket controle bien ce cote."""
        if side not in self.channels.get(channel_name, set()):
            return False
        self.engine.set_input(side, direction)
        return True


    async def start(self) -> None:
        async with self._lock:
            if self.task is not None:
                return
            self.started = True
            await database_sync_to_async(_mark_started)(self.match_id)
            self.task = asyncio.create_task(self._run(), name=f"match-{self.match_id}")

    async def _run(self) -> None:
        period = engine.DT
        next_at = time.monotonic()
        tick = 0

        try:
            while not self.finished:
                events = self.engine.tick()
                tick += 1

                if events:
                    self._record(events)
                    await self._broadcast({"type": "game.events", "events": events})

                if tick % SNAPSHOT_EVERY == 0 or events:
                    await self._broadcast({"type": "game.state",
                                           "state": self.engine.snapshot()})

                await self._check_presence()

                if self.engine.status == engine.STATUS_FINISHED:
                    await self._finish()
                    break

                next_at += period
                delay = next_at - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                else:
                    next_at = time.monotonic()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Boucle du match %s interrompue", self.match_id)
            await self._broadcast({"type": "game.error", "code": "engine_failure"})
        finally:
            self.finished = True

    def _record(self, events: list[dict]) -> None:
        """Retient l'instant de chaque point pour le tableau de bord de partie."""
        for event in events:
            if event["type"] != "score":
                continue
            self.points_log.append({
                "t": round(self.engine.tick_count * engine.DT, 1),
                "side": event["player"],
                "rally": event["rally"],
            })

    async def _check_presence(self) -> None:
        now = time.monotonic()

        if not self.channels:
            if self.engine.status != engine.STATUS_PAUSED:
                self.engine.pause()
            if self.empty_since is None:
                self.empty_since = now
            elif now - self.empty_since >= EMPTY_ROOM_TIMEOUT:
                await self._abort()
            return

        self.empty_since = None

        if self.mode != "remote" or not self.disconnected_since:
            return

        for side, since in list(self.disconnected_since.items()):
            elapsed = now - since
            if elapsed >= DISCONNECT_GRACE:
                logger.info("Match %s : forfait du joueur %s", self.match_id, side)
                self.engine.forfeit(loser=side)
                await self._broadcast({"type": "game.opponent", "status": "forfeit",
                                       "side": side})
                return
            if self.engine.status != engine.STATUS_PAUSED:
                self.engine.pause()
                await self._broadcast({
                    "type": "game.opponent",
                    "status": "left",
                    "side": side,
                    "seconds": round(DISCONNECT_GRACE - elapsed),
                })

    async def _abort(self) -> None:
        """Partie laissee a l'abandon : rien n'est enregistre comme resultat."""
        logger.info("Match %s abandonne faute de joueur connecte", self.match_id)
        self.finished = True
        try:
            await database_sync_to_async(services.abort_match)(self.match_id)
        except Exception:
            logger.exception("Abandon du match %s non enregistre", self.match_id)
        await self._broadcast({"type": "game.aborted"})

    async def _finish(self) -> None:
        snapshot = self.engine.snapshot()
        stats = self.engine.stats()
        forfeit = bool(self.disconnected_since)
        try:
            match = await database_sync_to_async(services.finish_match)(
                self.match_id, snapshot, stats, forfeit=forfeit,
                points_log=self.points_log,
            )
            payload = await database_sync_to_async(_match_payload)(match)
        except Exception:
            logger.exception("Enregistrement du resultat du match %s en echec", self.match_id)
            payload = None

        await self._broadcast({"type": "game.end", "state": snapshot,
                               "stats": stats, "match": payload})

    async def _broadcast(self, message: dict) -> None:
        await self._layer.group_send(self.group, message)

    async def stop(self) -> None:
        self.finished = True
        if self.task is not None and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.task = None


class RoomRegistry:
    """Index des parties vivantes, avec creation atomique."""

    def __init__(self) -> None:
        self._rooms: dict[str, MatchRoom] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, match) -> MatchRoom:
        key = str(match.id)
        async with self._lock:
            room = self._rooms.get(key)
            if room is None or room.finished:
                room = MatchRoom(key, mode=match.mode,
                                 points_to_win=match.points_to_win, seed=match.seed)
                self._rooms[key] = room
            return room

    def get(self, match_id) -> MatchRoom | None:
        return self._rooms.get(str(match_id))

    async def discard(self, match_id) -> None:
        async with self._lock:
            room = self._rooms.pop(str(match_id), None)
        if room is not None:
            await room.stop()

    async def shutdown(self) -> None:
        for match_id in list(self._rooms):
            await self.discard(match_id)


registry = RoomRegistry()



def _mark_started(match_id) -> None:
    from game.models import Match

    match = Match.objects.filter(pk=match_id).first()
    if match and match.state == Match.STATE_LOBBY:
        match.mark_started()


def _match_payload(match) -> dict:
    return match.to_dict()
