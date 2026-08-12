"""Tests des droits RGPD : export, anonymisation, effacement."""

from django.test import TestCase

from accounts import gdpr
from accounts.models import BackupCode, Friendship, RefreshToken, User
from chat.models import Block, Message
from game import services as game_services
from game.models import Match

PASSWORD = "Correct-Horse-42"


class GdprTestCase(TestCase):
    def setUp(self):
        self.ada = User.objects.create_user(email="ada@42.lu", display_name="Ada",
                                            password=PASSWORD)
        self.bob = User.objects.create_user(email="bob@42.lu", display_name="Bob",
                                            password=PASSWORD)

        # Un peu de vie : un match, un message, une amitie, un jeton.
        self.match = game_services.create_local_match(alias1="Ada", alias2="Bob",
                                                      points_to_win=3, user=self.ada)
        self.match.player2 = self.bob
        self.match.save(update_fields=["player2"])
        Message.objects.create(sender=self.ada, recipient=self.bob, body="salut")
        Friendship.objects.create(from_user=self.ada, to_user=self.bob,
                                  status=Friendship.ACCEPTED)
        Block.objects.create(blocker=self.ada, blocked=self.bob)
        RefreshToken.objects.create(user=self.ada, token_hash="x" * 64,
                                    expires_at=self.ada.date_joined)
        BackupCode.objects.create(user=self.ada, code_hash="y" * 64)

    def headers(self) -> dict:
        response = self.client.post("/api/auth/login", {"email": "ada@42.lu",
                                                        "password": PASSWORD},
                                    content_type="application/json")
        return {"HTTP_AUTHORIZATION": f"Bearer {response.json()['access_token']}"}


class ExportTest(GdprTestCase):
    def test_export_contains_every_category(self):
        payload = gdpr.export(self.ada)

        self.assertEqual(payload["account"]["email"], "ada@42.lu")
        for key in ("statistics", "matches", "tournaments", "messages_sent",
                    "friends", "blocked_users"):
            self.assertIn(key, payload)

    def test_export_never_leaks_secrets(self):
        self.ada.totp_secret = "SECRETBASE32"
        self.ada.save(update_fields=["totp_secret"])

        payload = gdpr.export(self.ada)
        serialised = str(payload)

        # Un fichier d'export circule par e-mail ou reste dans un dossier de
        # telechargements : il ne doit contenir aucun element rejouable.
        self.assertNotIn("SECRETBASE32", serialised)
        self.assertNotIn(self.ada.password, serialised)
        self.assertNotIn("argon2", serialised)

    def test_the_route_returns_a_downloadable_file(self):
        response = self.client.get("/api/me/data", **self.headers())

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("application/json", response["Content-Type"])

    def test_the_route_is_protected(self):
        self.assertEqual(self.client.get("/api/me/data").status_code, 401)


class AnonymizeTest(GdprTestCase):
    def test_identifying_fields_are_wiped(self):
        gdpr.anonymize(self.ada)
        self.ada.refresh_from_db()

        self.assertTrue(self.ada.is_anonymized)
        self.assertIsNone(self.ada.email)
        self.assertNotEqual(self.ada.display_name, "Ada")
        self.assertFalse(self.ada.is_active)
        self.assertIsNotNone(self.ada.anonymized_at)

    def test_the_frozen_alias_on_matches_is_replaced(self):
        """Un alias fige est un nom lisible : c'est une donnee personnelle."""
        gdpr.anonymize(self.ada)

        self.match.refresh_from_db()
        self.assertNotEqual(self.match.player1_alias, "Ada")
        self.assertIn("supprime", self.match.player1_alias)
        # Le match lui-meme survit : les statistiques de Bob restent justes.
        self.assertTrue(Match.objects.filter(pk=self.match.pk).exists())

    def test_message_content_is_erased_but_the_thread_survives(self):
        gdpr.anonymize(self.ada)

        message = Message.objects.get()
        self.assertEqual(message.body, "")
        self.assertEqual(message.recipient_id, self.bob.pk)

    def test_relations_sessions_and_second_factor_are_removed(self):
        gdpr.anonymize(self.ada)

        self.assertEqual(Friendship.objects.count(), 0)
        self.assertEqual(Block.objects.count(), 0)
        self.assertEqual(RefreshToken.objects.filter(user=self.ada).count(), 0)
        self.assertEqual(BackupCode.objects.filter(user=self.ada).count(), 0)

    def test_existing_tokens_stop_working(self):
        headers = self.headers()
        self.assertEqual(self.client.get("/api/me", **headers).status_code, 200)

        gdpr.anonymize(self.ada)
        self.assertEqual(self.client.get("/api/me", **headers).status_code, 401)

    def test_anonymizing_twice_is_harmless(self):
        gdpr.anonymize(self.ada)
        name = User.objects.get(pk=self.ada.pk).display_name
        gdpr.anonymize(User.objects.get(pk=self.ada.pk))
        self.assertEqual(User.objects.get(pk=self.ada.pk).display_name, name)

    def test_the_route_requires_the_password(self):
        headers = self.headers()

        refused = self.client.post("/api/me/anonymize", {"password": "pas-le-bon"},
                                   content_type="application/json", **headers)
        self.assertEqual(refused.status_code, 403)
        self.assertFalse(User.objects.get(pk=self.ada.pk).is_anonymized)

        accepted = self.client.post("/api/me/anonymize", {"password": PASSWORD},
                                    content_type="application/json", **headers)
        self.assertEqual(accepted.status_code, 200)
        self.assertTrue(User.objects.get(pk=self.ada.pk).is_anonymized)


class DeleteTest(GdprTestCase):
    def test_the_account_row_disappears(self):
        gdpr.delete_account(self.ada)
        self.assertFalse(User.objects.filter(pk=self.ada.pk).exists())

    def test_no_readable_trace_is_left_behind(self):
        """Supprimer la ligne ne suffit pas : les alias figes resteraient."""
        gdpr.delete_account(self.ada)

        self.match.refresh_from_db()
        self.assertNotEqual(self.match.player1_alias, "Ada")
        self.assertIsNone(self.match.player1_id)
        self.assertEqual(Message.objects.get().body, "")

    def test_the_opponent_keeps_their_history(self):
        gdpr.delete_account(self.ada)

        self.match.refresh_from_db()
        self.assertEqual(self.match.player2_id, self.bob.pk)
        self.assertEqual(self.match.player2_alias, "Bob")

    def test_the_route_requires_the_password(self):
        headers = self.headers()

        refused = self.client.post("/api/me/delete", {"password": "pas-le-bon"},
                                   content_type="application/json", **headers)
        self.assertEqual(refused.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.ada.pk).exists())

        accepted = self.client.post("/api/me/delete", {"password": PASSWORD},
                                    content_type="application/json", **headers)
        self.assertEqual(accepted.status_code, 200)
        self.assertFalse(User.objects.filter(pk=self.ada.pk).exists())


class PrivacySummaryTest(TestCase):
    def test_the_summary_is_public(self):
        response = self.client.get("/api/privacy")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["collected"])
        self.assertTrue(payload["rights"])
