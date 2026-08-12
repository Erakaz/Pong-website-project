"""Parcours complet de la double authentification, vu de l'API."""

from django.test import TestCase

from accounts import totp
from accounts.models import BackupCode, User

PASSWORD = "Correct-Horse-42"


class TwoFactorFlowTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ada@42.lu", display_name="Ada",
                                             password=PASSWORD)
        self.headers = self._login_headers()

    def _login_headers(self) -> dict:
        response = self.client.post("/api/auth/login", {
            "email": "ada@42.lu", "password": PASSWORD,
        }, content_type="application/json")
        return {"HTTP_AUTHORIZATION": f"Bearer {response.json()['access_token']}"}

    def _enable(self) -> list[str]:
        setup = self.client.post("/api/me/2fa/setup", "{}",
                                 content_type="application/json", **self.headers).json()
        code = totp.totp(setup["secret"])
        response = self.client.post("/api/me/2fa/enable", {"code": code},
                                    content_type="application/json", **self.headers)
        self.assertEqual(response.status_code, 200)
        return response.json()["backup_codes"]


    def test_setup_returns_a_scannable_uri(self):
        response = self.client.post("/api/me/2fa/setup", "{}",
                                    content_type="application/json", **self.headers)
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["otpauth_uri"].startswith("otpauth://totp/"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.totp_secret)
        self.assertFalse(self.user.totp_enabled)

    def test_enabling_requires_a_valid_code(self):
        self.client.post("/api/me/2fa/setup", "{}",
                         content_type="application/json", **self.headers)
        response = self.client.post("/api/me/2fa/enable", {"code": "000000"},
                                    content_type="application/json", **self.headers)

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.totp_enabled)

    def test_enabling_returns_backup_codes_and_stores_them_hashed(self):
        codes = self._enable()

        self.assertEqual(len(codes), totp.BACKUP_CODE_COUNT)
        stored = list(BackupCode.objects.filter(user=self.user).values_list("code_hash",
                                                                           flat=True))
        self.assertEqual(len(stored), totp.BACKUP_CODE_COUNT)
        for code in codes:
            self.assertNotIn(code, stored)
            self.assertIn(totp.hash_backup_code(code), stored)

    def test_enabling_closes_other_sessions(self):
        old_headers = dict(self.headers)
        self._enable()
        self.assertEqual(self.client.get("/api/me", **old_headers).status_code, 401)


    def test_password_alone_no_longer_opens_a_session(self):
        self._enable()
        response = self.client.post("/api/auth/login", {
            "email": "ada@42.lu", "password": PASSWORD,
        }, content_type="application/json")
        payload = response.json()

        self.assertTrue(payload["twofa_required"])
        self.assertNotIn("access_token", payload)
        self.assertIn("twofa_token", payload)

    def test_second_step_with_a_valid_code_opens_the_session(self):
        self._enable()
        self.user.refresh_from_db()

        login = self.client.post("/api/auth/login", {
            "email": "ada@42.lu", "password": PASSWORD,
        }, content_type="application/json").json()

        response = self.client.post("/api/auth/2fa/verify", {
            "twofa_token": login["twofa_token"],
            "code": totp.totp(self.user.totp_secret),
        }, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("access_token", response.json())

    def test_second_step_refuses_a_wrong_code(self):
        self._enable()
        login = self.client.post("/api/auth/login", {
            "email": "ada@42.lu", "password": PASSWORD,
        }, content_type="application/json").json()

        response = self.client.post("/api/auth/2fa/verify", {
            "twofa_token": login["twofa_token"], "code": "000000",
        }, content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_the_intermediate_token_cannot_be_used_as_an_access_token(self):
        """Un jeton de 2FA ne doit ouvrir aucune route de l'API."""
        self._enable()
        login = self.client.post("/api/auth/login", {
            "email": "ada@42.lu", "password": PASSWORD,
        }, content_type="application/json").json()

        response = self.client.get(
            "/api/me", HTTP_AUTHORIZATION=f"Bearer {login['twofa_token']}")
        self.assertEqual(response.status_code, 401)

    def test_verify_refuses_a_forged_intermediate_token(self):
        self._enable()
        response = self.client.post("/api/auth/2fa/verify", {
            "twofa_token": "pas.un.jeton", "code": "000000",
        }, content_type="application/json")
        self.assertEqual(response.status_code, 401)


    def test_a_backup_code_replaces_the_application_code(self):
        codes = self._enable()
        login = self.client.post("/api/auth/login", {
            "email": "ada@42.lu", "password": PASSWORD,
        }, content_type="application/json").json()

        response = self.client.post("/api/auth/2fa/verify", {
            "twofa_token": login["twofa_token"], "code": codes[0],
        }, content_type="application/json")
        self.assertEqual(response.status_code, 200)

    def test_a_backup_code_only_works_once(self):
        codes = self._enable()

        def attempt():
            login = self.client.post("/api/auth/login", {
                "email": "ada@42.lu", "password": PASSWORD,
            }, content_type="application/json").json()
            return self.client.post("/api/auth/2fa/verify", {
                "twofa_token": login["twofa_token"], "code": codes[0],
            }, content_type="application/json")

        self.assertEqual(attempt().status_code, 200)
        self.assertEqual(attempt().status_code, 400)

    def test_backup_code_is_accepted_whatever_its_formatting(self):
        codes = self._enable()
        login = self.client.post("/api/auth/login", {
            "email": "ada@42.lu", "password": PASSWORD,
        }, content_type="application/json").json()

        response = self.client.post("/api/auth/2fa/verify", {
            "twofa_token": login["twofa_token"],
            "code": codes[0].lower().replace("-", " "),
        }, content_type="application/json")
        self.assertEqual(response.status_code, 200)


    def test_disabling_requires_the_password(self):
        self._enable()
        headers = self._login_after_2fa()

        refused = self.client.post("/api/me/2fa/disable", {"password": "pas-le-bon"},
                                   content_type="application/json", **headers)
        self.assertEqual(refused.status_code, 403)

        accepted = self.client.post("/api/me/2fa/disable", {"password": PASSWORD},
                                    content_type="application/json", **headers)
        self.assertEqual(accepted.status_code, 200)

        self.user.refresh_from_db()
        self.assertFalse(self.user.totp_enabled)
        self.assertEqual(self.user.totp_secret, "")
        self.assertEqual(BackupCode.objects.filter(user=self.user).count(), 0)

    def _login_after_2fa(self) -> dict:
        self.user.refresh_from_db()
        login = self.client.post("/api/auth/login", {
            "email": "ada@42.lu", "password": PASSWORD,
        }, content_type="application/json").json()
        verified = self.client.post("/api/auth/2fa/verify", {
            "twofa_token": login["twofa_token"],
            "code": totp.totp(self.user.totp_secret),
        }, content_type="application/json").json()
        return {"HTTP_AUTHORIZATION": f"Bearer {verified['access_token']}"}

    def test_status_reports_the_remaining_backup_codes(self):
        codes = self._enable()
        headers = self._login_after_2fa()

        status = self.client.get("/api/me/2fa", **headers).json()
        self.assertTrue(status["enabled"])
        self.assertEqual(status["backup_codes_left"], len(codes))

    def test_routes_are_protected(self):
        for path in ["/api/me/2fa", "/api/me/2fa/setup", "/api/me/2fa/enable",
                     "/api/me/2fa/disable"]:
            method = self.client.get if path == "/api/me/2fa" else self.client.post
            self.assertEqual(method(path).status_code, 401, path)
