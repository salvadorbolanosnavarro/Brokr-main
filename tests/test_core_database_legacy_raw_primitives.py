"""Contracts for raw service-role primitives used to preserve legacy semantics."""
from __future__ import annotations

import inspect
import unittest

from core.database import get_service_json, patch_rows_no_response


class CoreDatabaseLegacyRawPrimitiveTests(unittest.TestCase):
    def test_get_service_json_preserves_raw_json_contract(self):
        sig = inspect.signature(get_service_json)
        self.assertIn("accepted_statuses", sig.parameters)
        self.assertIsNone(sig.parameters["accepted_statuses"].default)
        source = inspect.getsource(get_service_json)
        self.assertIn("headers=service_headers()", source)
        self.assertIn("_require_response_status(response, accepted_statuses)", source)
        self.assertIn("return response.json()", source)
        self.assertNotIn("isinstance", source)

    def test_status_only_patch_does_not_parse_response_body(self):
        sig = inspect.signature(patch_rows_no_response)
        self.assertEqual(sig.parameters["prefer"].default, "return=minimal")
        self.assertIn("accepted_statuses", sig.parameters)
        source = inspect.getsource(patch_rows_no_response)
        self.assertIn("headers=service_headers(prefer=prefer)", source)
        self.assertIn("_require_response_status(response, accepted_statuses)", source)
        self.assertNotIn("response.json", source)
        self.assertNotIn("return response", source)


if __name__ == "__main__":
    unittest.main()
