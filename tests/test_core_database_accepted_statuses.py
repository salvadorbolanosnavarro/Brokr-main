"""Contract tests for exact legacy status preservation in core.database writes."""
from __future__ import annotations

import unittest

import httpx

from core.database import _require_response_status


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


if __name__ == "__main__":
    unittest.main()
