import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from azure.core.exceptions import ResourceExistsError
import studies
import function_app


class StudyTests(unittest.TestCase):
    def test_irb_normalization(self):
        self.assertEqual(studies.normalize_irb(" irb-2026 / 001 "), "IRB2026001")
        self.assertEqual(studies.normalize_irb("IRB2026001"), "IRB2026001")

    def test_invalid_irb(self):
        for value in (None, "", " / ", "a", 123):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    studies.normalize_irb(value)

    @patch.dict(os.environ, {"RESEARCHPASS_STORAGE_CONNECTION": "UseDevelopmentStorage=true"})
    @patch("studies.TableServiceClient")
    def test_create_study_and_duplicate(self, service):
        table = service.from_connection_string.return_value.get_table_client.return_value
        result = studies.create_study(" irb-2026-001 ", " Synthetic study ", "test-user")
        self.assertEqual(result["study_title"], "Synthetic study")
        entity = table.create_entity.call_args.kwargs["entity"]
        self.assertEqual((entity["PartitionKey"], entity["RowKey"]), ("STUDY", "IRB2026001"))
        table.create_entity.side_effect = ResourceExistsError("already exists")
        with self.assertRaises(studies.DuplicateStudyError):
            studies.create_study("IRB2026001", "Synthetic study", "test-user")

    def test_missing_storage_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                studies.create_study("IRB2026001", "Synthetic study", "test-user")

    def test_invalid_title(self):
        with self.assertRaises(ValueError):
            studies.create_study("IRB2026001", " ", "test-user")

    @patch("function_app.create_study")
    def test_registration_success(self, create):
        import azure.functions as func
        create.return_value = {"irb_number": "IRB-2026-001", "study_title": "Synthetic", "study_status": "registered"}
        request = func.HttpRequest(method="POST", url="http://localhost/api/studies", body=json.dumps({"irb_number": "IRB-2026-001", "study_title": "Synthetic"}).encode())
        result = function_app.register_study(request)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(json.loads(result.get_body())["study_status"], "registered")

    def test_registration_invalid_json(self):
        import azure.functions as func
        request = func.HttpRequest(method="POST", url="http://localhost/api/studies", body=b"{broken")
        self.assertEqual(function_app.register_study(request).status_code, 400)

    @patch("function_app.create_study", side_effect=studies.DuplicateStudyError("duplicate"))
    def test_registration_duplicate(self, create):
        import azure.functions as func
        request = func.HttpRequest(method="POST", url="http://localhost/api/studies", body=b'{"irb_number":"IRB2026001","study_title":"Synthetic"}')
        self.assertEqual(function_app.register_study(request).status_code, 409)



if __name__ == "__main__":
    unittest.main()
