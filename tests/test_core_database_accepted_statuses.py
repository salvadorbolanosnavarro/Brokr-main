"""Contract tests for exact legacy status preservation in core.database writes."""
from __future__ import annotations

import inspect
import unittest

import httpx

from core.database import _require_response_status, patch_rows, post_rows


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

    def test_post_and_patch_expose_same_optional_exact_status_contract(self):
        post_sig = inspect.signature(post_rows)
        patch_sig = inspect.signature(patch_rows)
        self.assertIn("accepted_statuses", post_sig.parameters)
        self.assertIn("accepted_statuses", patch_sig.parameters)
        self.assertIsNone(post_sig.parameters["accepted_statuses"].default)
        self.assertIsNone(patch_sig.parameters["accepted_statuses"].default)
        self.assertIn("_require_response_status(response, accepted_statuses)", inspect.getsource(post_rows))
        self.assertIn("_require_response_status(response, accepted_statuses)", inspect.getsource(patch_rows))


if __name__ == "__main__":
    unittest.main()
