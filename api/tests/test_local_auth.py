import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import azure.functions as func
import local_auth
import function_app

SETTINGS = {
    "RESEARCHPASS_STORAGE_CONNECTION": "UseDevelopmentStorage=true",
    "RESEARCHPASS_SESSION_SECRET": "s" * 48,
    "RESEARCHPASS_INVITE_CODE": "i" * 30,
}

class LocalAccountTests(unittest.TestCase):
    def test_password_is_salted(self):
        salt1, hash1 = local_auth.password_hash("long-test-password-123")
        salt2, hash2 = local_auth.password_hash("long-test-password-123")
        self.assertNotEqual(salt1, salt2)
        self.assertNotEqual(hash1, hash2)

    def test_weak_password_rejected(self):
        with self.assertRaises(ValueError):
            local_auth.password_hash("short")

    @patch.dict(os.environ, SETTINGS)
    @patch("local_auth.users_table")
    def test_registration_uses_invitation_and_unique_email(self, table):
        with self.assertRaises(local_auth.LocalAuthError):
            local_auth.register("test@example.org", "long-test-password-123", "wrong")
        self.assertEqual(table.call_count, 0)
        result = local_auth.register("Test@Example.org", "long-test-password-123", SETTINGS["RESEARCHPASS_INVITE_CODE"])
        self.assertEqual(result["email"], "test@example.org")
        entity = table.return_value.create_entity.call_args.args[0]
        self.assertEqual(entity["RowKey"], "test@example.org")
        self.assertNotIn("password", entity)

    @patch.dict(os.environ, SETTINGS)
    @patch("local_auth.users_table")
    def test_login_and_session_validation(self, table):
        salt, digest = local_auth.password_hash("long-test-password-123")
        table.return_value.get_entity.return_value = {"user_id": "user-123", "salt": salt, "password_digest": digest, "active": True}
        token = local_auth.login("test@example.org", "long-test-password-123")["access_token"]
        req = func.HttpRequest(method="GET", url="http://localhost/api/studies/test/access", headers={"Authorization": "Bearer " + token}, body=b"")
        self.assertEqual(local_auth.authenticate(req), "user-123")
        with self.assertRaises(local_auth.LocalAuthError):
            local_auth.login("test@example.org", "wrong-password")

    def test_missing_configuration_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(local_auth.LocalAuthNotConfigured):
                local_auth.config()

if __name__ == "__main__":
    unittest.main()
