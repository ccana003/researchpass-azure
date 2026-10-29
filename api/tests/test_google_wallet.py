import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from google_wallet import generate_save_url


class GoogleWalletLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        cls.public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

    def _settings(self):
        return {
            "google_issuer_id": "1234567890123456789",
            "google_class_id": "researchpass_test",
            "platform_label": "Miami CTSI",
            "display_name": "Synthetic Study",
            "irb_number": "POC-2026-001",
        }

    def _env(self):
        return {
            "RESEARCHPASS_GOOGLE_SERVICE_ACCOUNT_JSON": json.dumps({
                "type": "service_account",
                "client_email": "wallet-test@example.iam.gserviceaccount.com",
                "private_key": self.private_pem,
            }),
            "RESEARCHPASS_WALLET_ORIGINS": "https://example.test",
        }

    def test_generates_signed_google_wallet_save_link(self):
        with patch.dict(os.environ, self._env(), clear=False):
            url = generate_save_url(self._settings(), "Synthetic Participant", "2026-01-01", "")
        self.assertTrue(url.startswith("https://pay.google.com/gp/v/save/"))
        token = url.rsplit("/", 1)[1]
        claims = jwt.decode(token, self.public_pem, algorithms=["RS256"], audience="google")
        self.assertEqual(claims["typ"], "savetowallet")
        self.assertEqual(claims["origins"], ["https://example.test"])
        wallet_payload = claims["payload"]
        self.assertEqual(wallet_payload["genericClasses"][0]["id"], "1234567890123456789.researchpass_test")
        obj = wallet_payload["genericObjects"][0]
        self.assertEqual(obj["classId"], "1234567890123456789.researchpass_test")
        self.assertEqual(obj["subheader"]["defaultValue"]["value"], "Synthetic Participant")
        self.assertEqual(obj["textModulesData"][-1]["body"], "2026-01-01")
        self.assertLessEqual(len(url), 8000)
        author = next(item for item in obj["textModulesData"] if item.get("id") == "institutional_author")
        self.assertEqual(author["header"], "Author")
        self.assertEqual(author["body"], "This pass was developed by the University of Miami CTSI with support from grant UM1TR004556 of the National Center for Advancing Translational Sciences.")

    def test_requires_service_account_configuration(self):
        with patch.dict(os.environ, {"RESEARCHPASS_GOOGLE_SERVICE_ACCOUNT_JSON": ""}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "not configured"):
                generate_save_url(self._settings(), "Synthetic Participant")

    def test_rejects_invalid_class_suffix(self):
        settings = self._settings()
        settings["google_class_id"] = "bad class suffix"
        with patch.dict(os.environ, self._env(), clear=False):
            with self.assertRaisesRegex(RuntimeError, "unsupported characters"):
                generate_save_url(settings, "Synthetic Participant")

    def test_rejects_missing_name(self):
        with patch.dict(os.environ, self._env(), clear=False):
            with self.assertRaisesRegex(ValueError, "participant name"):
                generate_save_url(self._settings(), "")


if __name__ == "__main__":
    unittest.main()
