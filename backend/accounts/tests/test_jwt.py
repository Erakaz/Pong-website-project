"""Tests du JWT maison."""

import base64
import json
import time

from django.test import SimpleTestCase, override_settings

from accounts import jwt_utils
from core.http import ApiError


def decode_segment(token: str, index: int) -> dict:
    segment = token.split(".")[index]
    padded = segment + "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def encode_segment(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


@override_settings(JWT_SECRET="secret-de-test", JWT_ISSUER="ft_transcendence")
class JwtTest(SimpleTestCase):
    def test_round_trip(self):
        token, ttl = jwt_utils.make_access_token(42)
        payload = jwt_utils.decode(token, expected_type=jwt_utils.TOKEN_TYPE_ACCESS)

        self.assertEqual(payload["sub"], "42")
        self.assertEqual(payload["iss"], "ft_transcendence")
        self.assertGreater(ttl, 0)
        self.assertEqual(jwt_utils.user_id_from_token(token), 42)

    def test_no_padding_in_segments(self):
        token, _ = jwt_utils.make_access_token(1)
        self.assertNotIn("=", token)

    def test_tampered_payload_is_rejected(self):
        token, _ = jwt_utils.make_access_token(1)
        header, _, signature = token.split(".")

        forged = f"{header}.{encode_segment({**decode_segment(token, 1), 'sub': '999'})}.{signature}"
        with self.assertRaises(ApiError):
            jwt_utils.decode(forged, expected_type=jwt_utils.TOKEN_TYPE_ACCESS)

    def test_algorithm_none_is_rejected(self):
        """Faille historique : accepter l'algorithme annonce par le jeton."""
        payload = {"iss": "ft_transcendence", "sub": "999",
                   "typ": jwt_utils.TOKEN_TYPE_ACCESS,
                   "iat": int(time.time()), "exp": int(time.time()) + 600}
        forged = f"{encode_segment({'alg': 'none', 'typ': 'JWT'})}.{encode_segment(payload)}."

        with self.assertRaises(ApiError):
            jwt_utils.decode(forged, expected_type=jwt_utils.TOKEN_TYPE_ACCESS)

    def test_signature_from_another_secret_is_rejected(self):
        token, _ = jwt_utils.make_access_token(1)
        with override_settings(JWT_SECRET="un-autre-secret"):
            with self.assertRaises(ApiError):
                jwt_utils.decode(token, expected_type=jwt_utils.TOKEN_TYPE_ACCESS)

    def test_expired_token_reports_its_own_code(self):
        token, ttl = jwt_utils.make_access_token(1, issued_at=int(time.time()) - 10_000)
        self.assertGreater(10_000, ttl)

        with self.assertRaises(ApiError) as caught:
            jwt_utils.decode(token, expected_type=jwt_utils.TOKEN_TYPE_ACCESS)
        self.assertEqual(caught.exception.code, "token_expired")

    def test_a_twofa_token_is_not_an_access_token(self):
        """Un jeton intermediaire de 2FA ne doit ouvrir aucune route."""
        token = jwt_utils.make_twofa_token(7)

        jwt_utils.decode(token, expected_type=jwt_utils.TOKEN_TYPE_TWOFA)
        with self.assertRaises(ApiError):
            jwt_utils.decode(token, expected_type=jwt_utils.TOKEN_TYPE_ACCESS)

    def test_issuer_is_checked(self):
        token, _ = jwt_utils.make_access_token(1)
        with override_settings(JWT_ISSUER="un-autre-site"):
            with self.assertRaises(ApiError):
                jwt_utils.decode(token, expected_type=jwt_utils.TOKEN_TYPE_ACCESS)

    def test_malformed_tokens_are_rejected_without_crashing(self):
        for value in ["", "abc", "a.b", "a.b.c.d", "...", None, 12, "a.b.c"]:
            with self.assertRaises(ApiError):
                jwt_utils.decode(value, expected_type=jwt_utils.TOKEN_TYPE_ACCESS)

    def test_each_token_has_a_distinct_identifier(self):
        first, _ = jwt_utils.make_access_token(1)
        second, _ = jwt_utils.make_access_token(1)
        self.assertNotEqual(decode_segment(first, 1)["jti"], decode_segment(second, 1)["jti"])
