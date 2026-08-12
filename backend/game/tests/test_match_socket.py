"""Tests de la WebSocket de partie : autorisations, deconnexion, forfait.

Ces tests pilotent le vrai consumer avec un communicateur Channels, ce qui
couvre le chemin complet — routage, authentification, salle, boucle asyncio —
sans navigateur.
"""

import asyncio

from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from accounts import jwt_utils
from accounts.models import User
from config.routing import websocket_urlpatterns
from game import rooms, services
from game.models import Match

PASSWORD = "Correct-Horse-42"


def application():
    return URLRouter(websocket_urlpatterns)


async def connect(match_id, token=None):
    """Ouvre une socket sur une partie et envoie le message `join`."""
    communicator = WebsocketCommunicator(application(), f"/ws/game/{match_id}")
    connected, _ = await communicator.connect()
    assert connected, "la socket n'a pas ete acceptee"
    await communicator.send_json_to({"type": "join", "token": token})
    return communicator


async def wait_for(communicator, kind, limit=40):
    """Consomme les messages jusqu'a en trouver un du type attendu."""
    for _ in range(limit):
        message = await communicator.receive_json_from(timeout=5)
        if message["type"] == kind:
            return message
    raise AssertionError(f"message « {kind} » jamais recu")


class LocalMatchSocketTest(TransactionTestCase):
    async def asyncTearDown(self):
        await rooms.registry.shutdown()

    async def test_a_local_match_gives_both_paddles_to_one_client(self):
        match = await database_sync_to_async(services.create_local_match)(
            alias1="Ada", alias2="Bob", points_to_win=3)

        communicator = await connect(match.id)
        joined = await wait_for(communicator, "joined")

        self.assertEqual(joined["sides"], [0, 1])
        self.assertIn("geometry", joined)
        await communicator.disconnect()
        await rooms.registry.shutdown()

    async def test_a_second_client_cannot_steal_a_local_match(self):
        match = await database_sync_to_async(services.create_local_match)(
            alias1="Ada", alias2="Bob", points_to_win=3)

        first = await connect(match.id)
        await wait_for(first, "joined")

        second = await connect(match.id)
        error = await wait_for(second, "error")
        self.assertEqual(error["code"], "seat_taken")

        await first.disconnect()
        await second.disconnect()
        await rooms.registry.shutdown()

    async def test_unknown_match_is_refused(self):
        communicator = await connect("00000000-0000-0000-0000-000000000000")
        error = await wait_for(communicator, "error")
        self.assertEqual(error["code"], "not_found")
        await communicator.disconnect()


class RemoteMatchSocketTest(TransactionTestCase):
    def setUp(self):
        self.bob = User.objects.create_user(email="bob@42.lu", display_name="Bob",
                                            password=PASSWORD)
        self.cyd = User.objects.create_user(email="cyd@42.lu", display_name="Cyd",
                                            password=PASSWORD)
        self.match = services.create_remote_match(user=self.bob, points_to_win=21)
        self.match.player2 = self.cyd
        self.match.save(update_fields=["player2"])

    def token(self, user) -> str:
        return jwt_utils.make_access_token(user.pk, version=user.token_version)[0]

    async def test_each_player_only_controls_their_own_paddle(self):
        bob = await connect(self.match.id, self.token(self.bob))
        cyd = await connect(self.match.id, self.token(self.cyd))

        self.assertEqual((await wait_for(bob, "joined"))["sides"], [0])
        self.assertEqual((await wait_for(cyd, "joined"))["sides"], [1])

        # Bob tente de bouger la raquette de Cyd.
        await bob.send_json_to({"type": "input", "side": 1, "dir": -1})
        error = await wait_for(bob, "error")
        self.assertEqual(error["code"], "forbidden_side")

        await bob.disconnect()
        await cyd.disconnect()
        await rooms.registry.shutdown()

    async def test_a_stranger_joins_as_a_spectator(self):
        intruder = await database_sync_to_async(User.objects.create_user)(
            email="eve@42.lu", display_name="Eve", password=PASSWORD)

        communicator = await connect(self.match.id, self.token(intruder))
        joined = await wait_for(communicator, "joined")

        # Aucune raquette : il regarde, il ne joue pas.
        self.assertEqual(joined["sides"], [])
        await communicator.send_json_to({"type": "input", "side": 0, "dir": -1})
        self.assertEqual((await wait_for(communicator, "error"))["code"], "forbidden_side")

        await communicator.disconnect()
        await rooms.registry.shutdown()

    async def test_the_match_starts_once_both_players_are_connected(self):
        bob = await connect(self.match.id, self.token(self.bob))
        await wait_for(bob, "joined")

        room = rooms.registry.get(self.match.id)
        self.assertIsNone(room.task, "la partie ne doit pas demarrer a un seul joueur")

        cyd = await connect(self.match.id, self.token(self.cyd))
        await wait_for(cyd, "joined")
        await wait_for(bob, "state")

        self.assertIsNotNone(rooms.registry.get(self.match.id).task)

        await bob.disconnect()
        await cyd.disconnect()
        await rooms.registry.shutdown()

    async def test_a_disconnection_pauses_the_game_and_warns_the_opponent(self):
        bob = await connect(self.match.id, self.token(self.bob))
        cyd = await connect(self.match.id, self.token(self.cyd))
        await wait_for(bob, "joined")
        await wait_for(cyd, "joined")
        await wait_for(bob, "state")

        await cyd.disconnect()

        message = await wait_for(bob, "opponent")
        self.assertEqual(message["status"], "left")
        self.assertEqual(message["side"], 1)
        # La partie est gelee : celui qui reste ne doit pas marquer pendant que
        # son adversaire tente de revenir.
        self.assertEqual(rooms.registry.get(self.match.id).engine.status, "paused")

        await bob.disconnect()
        await rooms.registry.shutdown()

    async def test_reconnecting_resumes_the_game(self):
        bob = await connect(self.match.id, self.token(self.bob))
        cyd = await connect(self.match.id, self.token(self.cyd))
        await wait_for(bob, "joined")
        await wait_for(cyd, "joined")
        await wait_for(bob, "state")

        await cyd.disconnect()
        left = await wait_for(bob, "opponent")
        self.assertEqual(left["status"], "left")

        again = await connect(self.match.id, self.token(self.cyd))
        await wait_for(again, "joined")

        back = await wait_for(bob, "opponent")
        self.assertEqual(back["status"], "back")
        # On reprend par un decompte, jamais balle en jeu : celui qui revient
        # doit avoir le temps de se replacer.
        self.assertEqual(rooms.registry.get(self.match.id).engine.status, "countdown")

        await bob.disconnect()
        await again.disconnect()
        await rooms.registry.shutdown()

    async def test_a_player_who_never_comes_back_loses_by_forfeit(self):
        original = rooms.DISCONNECT_GRACE
        rooms.DISCONNECT_GRACE = 0.3          # le test ne va pas attendre 20 s
        try:
            bob = await connect(self.match.id, self.token(self.bob))
            cyd = await connect(self.match.id, self.token(self.cyd))
            await wait_for(bob, "joined")
            await wait_for(cyd, "joined")
            await wait_for(bob, "state")

            await cyd.disconnect()

            end = await wait_for(bob, "end", limit=200)
            self.assertEqual(end["state"]["winner"], 0)

            # Laisse la boucle finir d'ecrire en base.
            await asyncio.sleep(0.3)
            match = await database_sync_to_async(Match.objects.get)(pk=self.match.id)
            self.assertEqual(match.state, Match.STATE_FINISHED)
            self.assertEqual(match.winner_side, 0)
            self.assertTrue(match.by_forfeit)

            await bob.disconnect()
        finally:
            rooms.DISCONNECT_GRACE = original
            await rooms.registry.shutdown()
