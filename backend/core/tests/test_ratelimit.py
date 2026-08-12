"""Tests du quota par adresse IP sur les routes d'authentification."""

from django.test import TestCase, override_settings

from accounts.models import User
from core import ratelimit

PASSWORD = "Correct-Horse-42"


class RateLimitTest(TestCase):
    def setUp(self):
        User.objects.create_user(email="ada@42.lu", display_name="Ada", password=PASSWORD)
        # Les compteurs sont un etat partage, en memoire ou dans Redis selon ce
        # qui est disponible : chaque cas doit repartir de zero, sans quoi les
        # tests se bloquent mutuellement des que Redis est joignable.
        ratelimit.reset()
        self.addCleanup(ratelimit.reset)

    def login(self, password=PASSWORD, ip="203.0.113.7"):
        return self.client.post("/api/auth/login", {"email": "ada@42.lu",
                                                    "password": password},
                                content_type="application/json", REMOTE_ADDR=ip)

    @override_settings(RATE_LIMITS={"login": (3, 300)})
    def test_repeated_attempts_are_eventually_refused(self):
        for _ in range(3):
            self.assertNotEqual(self.login("mauvais").status_code, 429)

        blocked = self.login("mauvais")
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.json()["error"]["code"], "rate_limited")
        self.assertIn("Retry-After", blocked)

    @override_settings(RATE_LIMITS={"login": (3, 300)})
    def test_the_quota_also_blocks_the_right_password(self):
        """Sinon il suffirait d'alterner pour contourner le comptage."""
        for _ in range(3):
            self.login("mauvais")
        self.assertEqual(self.login().status_code, 429)

    @override_settings(RATE_LIMITS={"login": (3, 300)})
    def test_the_quota_is_per_address(self):
        for _ in range(3):
            self.login("mauvais", ip="203.0.113.7")
        self.assertEqual(self.login("mauvais", ip="203.0.113.7").status_code, 429)
        # Un autre visiteur ne doit pas subir le blocage du premier.
        self.assertNotEqual(self.login("mauvais", ip="198.51.100.4").status_code, 429)

    @override_settings(RATE_LIMITS={})
    def test_no_quota_configured_means_no_limit(self):
        for _ in range(12):
            self.assertNotEqual(self.login("mauvais").status_code, 429)

    @override_settings(RATE_LIMITS={"login": (2, 300)})
    def test_other_routes_are_not_affected(self):
        for _ in range(3):
            self.login("mauvais")
        # /api/health n'est pas dans les seaux surveilles.
        self.assertEqual(self.client.get("/api/health").status_code, 200)


class ClientIdentityTest(TestCase):
    def test_the_forwarded_address_wins_over_the_socket(self):
        """nginx reecrit X-Forwarded-For ; c'est la vraie adresse du visiteur."""
        request = type("R", (), {"META": {
            "HTTP_X_FORWARDED_FOR": "203.0.113.7, 10.0.0.1",
            "REMOTE_ADDR": "172.18.0.5",
        }})()
        self.assertEqual(ratelimit.client_identity(request), "203.0.113.7")

    def test_it_falls_back_to_the_socket_address(self):
        request = type("R", (), {"META": {"REMOTE_ADDR": "172.18.0.5"}})()
        self.assertEqual(ratelimit.client_identity(request), "172.18.0.5")

    def test_an_oversized_header_is_truncated(self):
        request = type("R", (), {"META": {"HTTP_X_FORWARDED_FOR": "x" * 500}})()
        self.assertLessEqual(len(ratelimit.client_identity(request)), 45)
