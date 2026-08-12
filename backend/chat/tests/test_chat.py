"""Tests de la messagerie : envoi, blocage, invitation, annonces de tournoi."""

from django.test import TestCase

from accounts.models import User
from chat import services
from chat.models import Block, Message
from core.http import ApiError
from game import services as game_services
from game.models import Match

PASSWORD = "Correct-Horse-42"


class ChatTestCase(TestCase):
    def setUp(self):
        self.ada = User.objects.create_user(email="ada@42.lu", display_name="Ada",
                                            password=PASSWORD)
        self.bob = User.objects.create_user(email="bob@42.lu", display_name="Bob",
                                            password=PASSWORD)

    def as_ada(self) -> dict:
        response = self.client.post("/api/auth/login", {"email": "ada@42.lu",
                                                        "password": PASSWORD},
                                    content_type="application/json")
        return {"HTTP_AUTHORIZATION": f"Bearer {response.json()['access_token']}"}


class MessagingTest(ChatTestCase):
    def test_a_message_is_stored_and_returned(self):
        response = self.client.post(f"/api/chat/with/{self.bob.pk}", {"body": "salut"},
                                    content_type="application/json", **self.as_ada())

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["message"]["body"], "salut")
        self.assertEqual(Message.objects.count(), 1)

    def test_the_thread_is_shared_by_both_participants(self):
        services.send_message(self.ada, self.bob, "salut")
        services.send_message(self.bob, self.ada, "salut toi")

        for user, other in ((self.ada, self.bob), (self.bob, self.ada)):
            thread = services.conversation(user, other)
            self.assertEqual([message.body for message in thread], ["salut", "salut toi"])

    def test_empty_message_is_refused(self):
        with self.assertRaises(ApiError):
            services.send_message(self.ada, self.bob, "   ")

    def test_message_length_is_capped(self):
        with self.assertRaises(ApiError):
            services.send_message(self.ada, self.bob, "x" * (services.MESSAGE_MAX_LENGTH + 1))

    def test_writing_to_yourself_is_refused(self):
        with self.assertRaises(ApiError):
            services.send_message(self.ada, self.ada, "salut")

    def test_invisible_characters_are_stripped(self):
        # U+202E inverse le sens de lecture du texte qui suit (de quoi
        # afficher un message trompeur), et un octet nul casse certains
        # traitements en aval. Les deux sont retires a la validation.
        payload = "sa" + chr(0x202E) + "lut" + chr(0)
        message = services.send_message(self.ada, self.bob, payload)
        self.assertEqual(message.body, "salut")

    def test_reading_a_thread_marks_it_as_read(self):
        services.send_message(self.bob, self.ada, "salut")
        self.assertEqual(services.unread_count(self.ada), 1)

        self.client.get(f"/api/chat/with/{self.bob.pk}", **self.as_ada())
        self.assertEqual(services.unread_count(self.ada), 0)

    def test_routes_are_protected(self):
        self.assertEqual(self.client.get("/api/chat/conversations").status_code, 401)
        self.assertEqual(self.client.get(f"/api/chat/with/{self.bob.pk}").status_code, 401)


class BlockTest(ChatTestCase):
    def test_a_blocked_sender_cannot_reach_the_recipient(self):
        Block.objects.create(blocker=self.ada, blocked=self.bob)

        with self.assertRaises(ApiError) as caught:
            services.send_message(self.bob, self.ada, "coucou")

        self.assertEqual(caught.exception.code, "not_delivered")
        self.assertEqual(Message.objects.count(), 0)

    def test_blocking_cuts_the_conversation_both_ways(self):
        """Sinon, celui qui bloque pourrait continuer a ecrire : incoherent, et
        cela revelerait le blocage a l'autre."""
        Block.objects.create(blocker=self.ada, blocked=self.bob)
        with self.assertRaises(ApiError):
            services.send_message(self.ada, self.bob, "et moi ?")

    def test_the_block_is_enforced_by_the_api_not_only_the_interface(self):
        Block.objects.create(blocker=self.bob, blocked=self.ada)

        response = self.client.post(f"/api/chat/with/{self.bob.pk}", {"body": "coucou"},
                                    content_type="application/json", **self.as_ada())
        self.assertEqual(response.status_code, 403)

    def test_a_blocked_conversation_disappears_from_the_list(self):
        services.send_message(self.ada, self.bob, "salut")
        self.assertEqual(len(services.conversations(self.ada)), 1)

        services.set_block(self.ada, self.bob, True)
        self.assertEqual(services.conversations(self.ada), [])
        self.assertEqual(services.conversations(self.bob), [])

    def test_unblocking_restores_the_conversation(self):
        services.send_message(self.ada, self.bob, "salut")
        services.set_block(self.ada, self.bob, True)
        services.set_block(self.ada, self.bob, False)

        self.assertEqual(len(services.conversations(self.ada)), 1)

    def test_blocking_yourself_is_refused(self):
        with self.assertRaises(ApiError):
            services.set_block(self.ada, self.ada, True)

    def test_blocking_twice_is_harmless(self):
        services.set_block(self.ada, self.bob, True)
        services.set_block(self.ada, self.bob, True)
        self.assertEqual(Block.objects.count(), 1)


class InviteTest(ChatTestCase):
    def test_an_invitation_creates_a_match_and_a_message(self):
        response = self.client.post(f"/api/chat/with/{self.bob.pk}/invite", "{}",
                                    content_type="application/json", **self.as_ada())

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["message"]["kind"], Message.KIND_INVITE)

        match = Match.objects.get(pk=payload["match"]["id"])
        self.assertEqual(match.mode, Match.MODE_REMOTE)
        # Les deux places sont deja attribuees : l'invite n'a rien a chercher.
        self.assertEqual(match.player1_id, self.ada.pk)
        self.assertEqual(match.player2_id, self.bob.pk)

    def test_a_blocked_player_cannot_be_invited(self):
        Block.objects.create(blocker=self.bob, blocked=self.ada)
        response = self.client.post(f"/api/chat/with/{self.bob.pk}/invite", "{}",
                                    content_type="application/json", **self.as_ada())
        self.assertEqual(response.status_code, 403)


class TournamentAnnouncementTest(ChatTestCase):
    def test_players_are_warned_of_their_next_match(self):
        """« The tournament system should be able to warn users expected for
        the next game. »"""
        tournament = game_services.create_tournament(
            name="Coupe", mode="remote", points_to_win=3,
            entries=[{"user": self.ada, "alias": "Ada"}, {"user": self.bob, "alias": "Bob"}],
            creator=self.ada,
        )
        game_services.start_tournament(tournament)

        for user in (self.ada, self.bob):
            announcements = Message.objects.filter(recipient=user, kind=Message.KIND_SYSTEM)
            self.assertEqual(announcements.count(), 1, f"aucune annonce pour {user}")
            announcement = announcements.get()
            self.assertIsNone(announcement.sender_id)     # message du systeme
            self.assertIsNotNone(announcement.match_id)   # avec le lien vers le match

    def test_an_announcement_reaches_a_blocked_pair_anyway(self):
        """Un blocage entre joueurs ne doit pas empecher le tournoi de les
        convoquer : l'annonce vient du systeme, pas de l'adversaire."""
        Block.objects.create(blocker=self.ada, blocked=self.bob)

        tournament = game_services.create_tournament(
            name="Coupe", mode="remote", points_to_win=3,
            entries=[{"user": self.ada, "alias": "Ada"}, {"user": self.bob, "alias": "Bob"}],
            creator=self.ada,
        )
        game_services.start_tournament(tournament)

        self.assertEqual(
            Message.objects.filter(kind=Message.KIND_SYSTEM).count(), 2)
