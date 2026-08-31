"""Contract tests for exact legacy status preservation in core.database writes."""
from __future__ import annotations

import inspect
import unittest

import httpx

from core.database import (
    _require_response_status,
    delete_rows,
    patch_rows,
    post_rows,
    upsert_rows,
)


class CoreDatabaseAcceptedStatusesTests(unittest.TestCase):
    @staticmethod
    def response(status: int) -> httpx.Response:
        return httpx.Response(status, request=httpx.Request("POST", "https://example.test/rest/v1/demo"))

    def test_default_behavior_accepts_any_2xx(self):
        _require_response_status(self.response(200))
        _require_response_status(self.response(202))
        _require_response_status(self.response(204))

    def test_explicit_status_set_accepts_only_members(self):
        _require_response_status(self.response(200), (200, 201))
        _require_response_status(self.response(201), (200, 201))
        with self.assertRaises(httpx.HTTPStatusError) as ctx:
            _require_response_status(self.response(204), (200, 201))
        self.assertEqual(ctx.exception.response.status_code, 204)

    def test_real_http_errors_still_raise_with_response(self):
        with self.assertRaises(httpx.HTTPStatusError) as ctx:
            _require_response_status(self.response(500), (200, 201))
        self.assertEqual(ctx.exception.response.status_code, 500)

    def test_write_helpers_expose_same_optional_exact_status_contract(self):
        for helper in (post_rows, patch_rows, upsert_rows, delete_rows):
            with self.subTest(helper=helper.__name__):
                signature = inspect.signature(helper)
                self.assertIn("accepted_statuses", signature.parameters)
                self.assertIsNone(signature.parameters["accepted_statuses"].default)
                self.assertIn(
                    "_require_response_status(response, accepted_statuses)",
                    inspect.getsource(helper),
                )

    def test_delete_rows_preserves_old_defaults_but_can_send_prefer(self):
        signature = inspect.signature(delete_rows)
        self.assertIn("prefer", signature.parameters)
        self.assertIsNone(signature.parameters["prefer"].default)
        source = inspect.getsource(delete_rows)
        self.assertIn("headers=service_headers(prefer=prefer)", source)


if __name__ == "__main__":
    unittest.main()
