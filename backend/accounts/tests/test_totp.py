"""Tests du TOTP maison, valides contre les vecteurs officiels de la RFC 6238."""

import base64
import time
import unittest

from accounts import totp

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode("ascii")

RFC_VECTORS = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
]


class RfcComplianceTest(unittest.TestCase):
    def test_official_test_vectors(self):
        for timestamp, expected in RFC_VECTORS:
            with self.subTest(timestamp=timestamp):
                self.assertEqual(totp.totp(RFC_SECRET, at=timestamp, digits=8), expected)

    def test_hotp_matches_rfc4226_first_values(self):
        expected = ["755224", "287082", "359152", "969429", "338314"]
        for counter, code in enumerate(expected):
            self.assertEqual(totp.hotp(RFC_SECRET, counter), code)


class VerificationTest(unittest.TestCase):
    def setUp(self):
        self.secret = totp.generate_secret()
        self.now = 1_700_000_000

    def test_current_code_is_accepted(self):
        code = totp.totp(self.secret, at=self.now)
        self.assertTrue(totp.verify(self.secret, code, at=self.now))

    def test_previous_and_next_slices_are_tolerated(self):
        """L'horloge d'un telephone derive : une tranche de part et d'autre."""
        for offset in (-totp.PERIOD, totp.PERIOD):
            code = totp.totp(self.secret, at=self.now + offset)
            self.assertTrue(totp.verify(self.secret, code, at=self.now))

    def test_older_codes_are_refused(self):
        code = totp.totp(self.secret, at=self.now - 5 * totp.PERIOD)
        self.assertFalse(totp.verify(self.secret, code, at=self.now))

    def test_a_code_from_another_secret_is_refused(self):
        other = totp.generate_secret()
        self.assertFalse(totp.verify(self.secret, totp.totp(other, at=self.now), at=self.now))

    def test_malformed_input_is_refused_without_crashing(self):
        for value in ["", "abcdef", "12345", "1234567", None, 123456, "12 34 56 78"]:
            self.assertFalse(totp.verify(self.secret, value, at=self.now))

    def test_spaces_in_the_typed_code_are_ignored(self):
        code = totp.totp(self.secret, at=self.now)
        spaced = f"{code[:3]} {code[3:]}"
        self.assertTrue(totp.verify(self.secret, spaced, at=self.now))

    def test_empty_secret_never_validates(self):
        self.assertFalse(totp.verify("", "123456", at=self.now))


class SecretTest(unittest.TestCase):
    def test_secret_is_valid_base32_and_long_enough(self):
        secret = totp.generate_secret()
        padded = secret + "=" * (-len(secret) % 8)
        self.assertEqual(len(base64.b32decode(padded)), totp.SECRET_BYTES)

    def test_two_secrets_differ(self):
        self.assertNotEqual(totp.generate_secret(), totp.generate_secret())

    def test_provisioning_uri_carries_everything_an_app_needs(self):
        secret = totp.generate_secret()
        uri = totp.provisioning_uri(secret, "ada@42.lu")

        self.assertTrue(uri.startswith("otpauth://totp/"))
        self.assertIn(f"secret={secret}", uri)
        self.assertIn("issuer=ft_transcendence", uri)
        self.assertIn("digits=6", uri)
        self.assertIn("period=30", uri)

    def test_provisioning_uri_escapes_the_account(self):
        uri = totp.provisioning_uri("ABCD", "a b/c@42.lu")
        self.assertNotIn(" ", uri)
        self.assertEqual(uri.count("/"), 3)
        self.assertIn("a%20b%2Fc%4042.lu", uri)


class BackupCodeTest(unittest.TestCase):
    def test_codes_are_unique_and_well_formed(self):
        codes = totp.generate_backup_codes()
        self.assertEqual(len(codes), totp.BACKUP_CODE_COUNT)
        self.assertEqual(len(set(codes)), totp.BACKUP_CODE_COUNT)
        for code in codes:
            self.assertRegex(code, r"^[A-Z2-7]{4}-[A-Z2-7]{4}$")

    def test_hash_is_insensitive_to_formatting(self):
        code = totp.generate_backup_codes(1)[0]
        variants = [code, code.lower(), code.replace("-", ""), f" {code} "]
        hashes = {totp.hash_backup_code(variant) for variant in variants}
        self.assertEqual(len(hashes), 1)

    def test_hash_is_not_reversible_to_the_code(self):
        code = totp.generate_backup_codes(1)[0]
        digest = totp.hash_backup_code(code)
        self.assertEqual(len(digest), 64)
        self.assertNotIn(totp.normalize_backup_code(code), digest)


class ClockTest(unittest.TestCase):
    def test_code_changes_between_slices(self):
        secret = totp.generate_secret()
        base = int(time.time() // totp.PERIOD) * totp.PERIOD
        self.assertNotEqual(totp.totp(secret, at=base),
                            totp.totp(secret, at=base + totp.PERIOD))

    def test_code_is_stable_within_a_slice(self):
        secret = totp.generate_secret()
        base = int(time.time() // totp.PERIOD) * totp.PERIOD
        self.assertEqual(totp.totp(secret, at=base),
                         totp.totp(secret, at=base + totp.PERIOD - 1))


if __name__ == "__main__":
    unittest.main()
