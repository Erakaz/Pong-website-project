"""Tests des parcours d'authentification et de la rotation des sessions."""

import io

from django.test import Client, TestCase
from PIL import Image

from accounts import tokens
from accounts.avatars import process as process_avatar
from accounts.models import Friendship, RefreshToken, User
from core.http import ApiError

PASSWORD = "Correct-Horse-42"


def make_user(display_name="Ada", email="ada@42.lu", password=PASSWORD) -> User:
    return User.objects.create_user(email=email, display_name=display_name, password=password)


def image_bytes(size=(64, 64), image_format="PNG", color=(200, 30, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=image_format)
    return buffer.getvalue()


class Upload:
    """Substitut minimal d'un fichier televerse par Django."""

    def __init__(self, payload: bytes):
        self._payload = payload
        self.size = len(payload)

    def read(self) -> bytes:
        return self._payload


class RegistrationTest(TestCase):
    def test_registration_creates_a_session(self):
        response = self.client.post("/api/auth/register", {
            "display_name": "Ada", "email": "ada@42.lu", "password": PASSWORD,
        }, content_type="application/json")

        self.assertEqual(response.status_code, 201)
        self.assertIn("access_token", response.json())
        # Les deux cookies de session sont poses des l'inscription.
        self.assertIn("ftt_refresh", response.cookies)
        self.assertIn("ftt_csrf", response.cookies)

    def test_refresh_cookie_is_http_only_and_scoped(self):
        response = self.client.post("/api/auth/register", {
            "display_name": "Ada", "email": "ada@42.lu", "password": PASSWORD,
        }, content_type="application/json")

        cookie = response.cookies["ftt_refresh"]
        # httpOnly : hors de portee du JavaScript, donc d'une XSS.
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        # Envoye uniquement aux routes d'authentification.
        self.assertEqual(cookie["path"], "/api/auth")

    def test_csrf_cookie_stays_readable_by_javascript(self):
        response = self.client.post("/api/auth/register", {
            "display_name": "Ada", "email": "ada@42.lu", "password": PASSWORD,
        }, content_type="application/json")
        # La double soumission suppose que le JS puisse lire ce cookie.
        self.assertFalse(response.cookies["ftt_csrf"]["httponly"])

    def test_password_is_hashed_with_argon2(self):
        self.client.post("/api/auth/register", {
            "display_name": "Ada", "email": "ada@42.lu", "password": PASSWORD,
        }, content_type="application/json")

        user = User.objects.get(email="ada@42.lu")
        self.assertTrue(user.password.startswith("argon2$"))
        self.assertNotIn(PASSWORD, user.password)

    def test_email_is_normalised(self):
        self.client.post("/api/auth/register", {
            "display_name": "Ada", "email": "  ADA@42.LU ", "password": PASSWORD,
        }, content_type="application/json")
        self.assertTrue(User.objects.filter(email="ada@42.lu").exists())

    def test_duplicate_email_is_refused(self):
        make_user()
        response = self.client.post("/api/auth/register", {
            "display_name": "Autre", "email": "ada@42.lu", "password": PASSWORD,
        }, content_type="application/json")
        self.assertEqual(response.status_code, 409)

    def test_duplicate_display_name_is_refused(self):
        make_user()
        response = self.client.post("/api/auth/register", {
            "display_name": "Ada", "email": "autre@42.lu", "password": PASSWORD,
        }, content_type="application/json")
        self.assertEqual(response.status_code, 409)


class LoginTest(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_valid_credentials(self):
        response = self.client.post("/api/auth/login", {
            "email": "ada@42.lu", "password": PASSWORD,
        }, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["display_name"], "Ada")

    def test_wrong_password(self):
        response = self.client.post("/api/auth/login", {
            "email": "ada@42.lu", "password": "pas-le-bon",
        }, content_type="application/json")
        self.assertEqual(response.status_code, 401)

    def test_unknown_account_answers_like_a_wrong_password(self):
        """Meme code et meme message : l'API ne dit pas qui est inscrit."""
        unknown = self.client.post("/api/auth/login", {
            "email": "personne@42.lu", "password": PASSWORD,
        }, content_type="application/json")
        wrong = self.client.post("/api/auth/login", {
            "email": "ada@42.lu", "password": "pas-le-bon",
        }, content_type="application/json")

        self.assertEqual(unknown.status_code, wrong.status_code)
        self.assertEqual(unknown.json()["error"]["code"], wrong.json()["error"]["code"])

    def test_disabled_account_cannot_log_in(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post("/api/auth/login", {
            "email": "ada@42.lu", "password": PASSWORD,
        }, content_type="application/json")
        self.assertEqual(response.status_code, 403)


class ProtectedRouteTest(TestCase):
    def setUp(self):
        self.user = make_user()

    def auth_header(self) -> dict:
        response = self.client.post("/api/auth/login", {
            "email": "ada@42.lu", "password": PASSWORD,
        }, content_type="application/json")
        return {"HTTP_AUTHORIZATION": f"Bearer {response.json()['access_token']}"}

    def test_route_requires_a_token(self):
        self.assertEqual(self.client.get("/api/me").status_code, 401)

    def test_route_accepts_a_valid_token(self):
        self.assertEqual(self.client.get("/api/me", **self.auth_header()).status_code, 200)

    def test_revoking_sessions_invalidates_existing_tokens(self):
        headers = self.auth_header()
        self.assertEqual(self.client.get("/api/me", **headers).status_code, 200)

        # La generation de jetons avance : tout jeton portant l'ancienne est
        # refuse, sans liste noire a maintenir et sans dependre de l'horloge.
        self.user.revoke_all_tokens()

        response = self.client.get("/api/me", **headers)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "token_revoked")

    def test_changing_the_password_keeps_the_current_session_alive(self):
        """La revocation ne doit pas ejecter celui qui vient de la declencher."""
        headers = self.auth_header()

        response = self.client.post("/api/me/password", {
            "current_password": PASSWORD, "password": "Nouveau-Mot-2De-Passe",
        }, content_type="application/json", **headers)
        self.assertEqual(response.status_code, 200)

        # L'ancien jeton est mort, le nouveau fonctionne.
        self.assertEqual(self.client.get("/api/me", **headers).status_code, 401)
        fresh = {"HTTP_AUTHORIZATION": f"Bearer {response.json()['access_token']}"}
        self.assertEqual(self.client.get("/api/me", **fresh).status_code, 200)

    def test_garbage_authorization_header_is_rejected(self):
        for value in ["", "Bearer", "Basic abc", "Bearer  ", "abc.def.ghi"]:
            response = self.client.get("/api/me", HTTP_AUTHORIZATION=value)
            self.assertEqual(response.status_code, 401, value)


class RefreshRotationTest(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_rotation_replaces_the_token(self):
        raw = tokens.issue(self.user)
        raw_next, user = tokens.rotate(raw)

        self.assertNotEqual(raw, raw_next)
        self.assertEqual(user.pk, self.user.pk)
        self.assertEqual(RefreshToken.objects.count(), 2)

    def test_the_raw_token_is_never_stored(self):
        raw = tokens.issue(self.user)
        stored = RefreshToken.objects.get()
        self.assertNotEqual(stored.token_hash, raw)
        self.assertEqual(len(stored.token_hash), 64)      # SHA-256 en hexadecimal

    def test_replaying_a_used_token_kills_the_whole_session(self):
        """Detection de rejeu : un jeton vole ne sert qu'une fois."""
        raw = tokens.issue(self.user)
        raw_next, _ = tokens.rotate(raw)

        with self.assertRaises(ApiError) as caught:
            tokens.rotate(raw)                            # rejeu de l'ancien
        self.assertEqual(caught.exception.code, "refresh_reused")

        # Y compris le jeton legitime issu de la rotation : toute la chaine
        # tombe, l'utilisateur devra se reconnecter.
        with self.assertRaises(ApiError):
            tokens.rotate(raw_next)

    def test_unknown_token_is_rejected(self):
        with self.assertRaises(ApiError):
            tokens.rotate("jeton-invente")

    def test_revoked_token_is_rejected(self):
        raw = tokens.issue(self.user)
        tokens.revoke(raw)
        with self.assertRaises(ApiError):
            tokens.rotate(raw)


class CsrfTest(TestCase):
    def setUp(self):
        make_user()
        self.client.post("/api/auth/login", {"email": "ada@42.lu", "password": PASSWORD},
                         content_type="application/json")

    def test_refresh_without_the_header_is_refused(self):
        response = self.client.post("/api/auth/refresh")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "csrf_failed")

    def test_refresh_with_a_wrong_header_is_refused(self):
        response = self.client.post("/api/auth/refresh", HTTP_X_CSRF_TOKEN="pas-le-bon")
        self.assertEqual(response.status_code, 403)

    def test_refresh_with_the_matching_header_succeeds(self):
        cookie = self.client.cookies["ftt_csrf"].value
        response = self.client.post("/api/auth/refresh", HTTP_X_CSRF_TOKEN=cookie)
        self.assertEqual(response.status_code, 200)


class AvatarTest(TestCase):
    def test_a_jpeg_is_re_encoded_to_png(self):
        result = process_avatar(Upload(image_bytes(image_format="JPEG")))
        self.assertTrue(result.read().startswith(b"\x89PNG"))

    def test_a_non_image_is_refused(self):
        # Un script deguise en avatar : Pillow ne le decode pas.
        with self.assertRaises(ApiError):
            process_avatar(Upload(b"<?php system($_GET['c']); ?>"))

    def test_an_oversized_file_is_refused(self):
        payload = Upload(image_bytes())
        payload.size = 5 * 1024 * 1024
        with self.assertRaises(ApiError):
            process_avatar(payload)

    def test_an_empty_file_is_refused(self):
        with self.assertRaises(ApiError):
            process_avatar(Upload(b""))

    def test_result_is_square_and_bounded(self):
        result = process_avatar(Upload(image_bytes(size=(1200, 400))))
        with Image.open(io.BytesIO(result.read())) as image:
            self.assertEqual(image.width, image.height)
            self.assertLessEqual(image.width, 512)

    def test_exif_metadata_does_not_survive(self):
        # Une photo de telephone embarque souvent des coordonnees GPS.
        buffer = io.BytesIO()
        source = Image.new("RGB", (64, 64), (10, 20, 30))
        exif = source.getexif()
        exif[0x010F] = "SecretCamera"
        source.save(buffer, format="JPEG", exif=exif)

        result = process_avatar(Upload(buffer.getvalue()))
        with Image.open(io.BytesIO(result.read())) as image:
            self.assertFalse(dict(image.getexif()))


class FriendshipTest(TestCase):
    def setUp(self):
        self.ada = make_user()
        self.bob = make_user(display_name="Bob", email="bob@42.lu")
        self.client = Client()
        response = self.client.post("/api/auth/login", {"email": "ada@42.lu",
                                                        "password": PASSWORD},
                                    content_type="application/json")
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {response.json()['access_token']}"}

    def test_request_then_accept(self):
        response = self.client.post("/api/friends", {"display_name": "Bob"},
                                    content_type="application/json", **self.headers)
        self.assertEqual(response.status_code, 201)

        link = Friendship.objects.get()
        self.assertEqual(link.status, Friendship.PENDING)

        link.status = Friendship.ACCEPTED
        link.save(update_fields=["status"])

        listing = self.client.get("/api/friends", **self.headers).json()
        self.assertEqual(len(listing["friends"]), 1)
        self.assertEqual(listing["friends"][0]["user"]["display_name"], "Bob")

    def test_cannot_befriend_yourself(self):
        response = self.client.post("/api/friends", {"display_name": "Ada"},
                                    content_type="application/json", **self.headers)
        self.assertEqual(response.status_code, 400)

    def test_crossed_requests_become_a_friendship(self):
        Friendship.objects.create(from_user=self.bob, to_user=self.ada)

        response = self.client.post("/api/friends", {"display_name": "Bob"},
                                    content_type="application/json", **self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Friendship.objects.get().status, Friendship.ACCEPTED)

    def test_duplicate_request_is_refused(self):
        self.client.post("/api/friends", {"display_name": "Bob"},
                         content_type="application/json", **self.headers)
        response = self.client.post("/api/friends", {"display_name": "Bob"},
                                    content_type="application/json", **self.headers)
        self.assertEqual(response.status_code, 409)

    def test_friends_route_is_protected(self):
        self.assertEqual(Client().get("/api/friends").status_code, 401)
