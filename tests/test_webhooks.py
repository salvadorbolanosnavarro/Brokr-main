"""Regression tests for shared webhook authentication."""
import unittest

from fastapi import HTTPException
from starlette.requests import Request

from core.webhooks import require_shared_secret


def _request(*, token_header: str = "", query: str = "") -> Request:
    headers = []
    if token_header:
        headers.append((b"x-broquer-token", token_header.encode("utf-8")))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/webhook/correo-entrante",
            "headers": headers,
            "query_string": query.encode("utf-8"),
        }
    )


class SharedSecretTests(unittest.TestCase):
    def test_missing_server_secret_fails_closed(self):
        with self.assertRaises(HTTPException) as ctx:
            require_shared_secret(_request(), "")
        self.assertEqual(ctx.exception.status_code, 503)

    def test_wrong_secret_is_denied(self):
        with self.assertRaises(HTTPException) as ctx:
            require_shared_secret(_request(token_header="wrong"), "correct")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_header_secret_is_accepted(self):
        self.assertIsNone(
            require_shared_secret(_request(token_header="correct"), "correct")
        )

    def test_query_secret_remains_backwards_compatible(self):
        self.assertIsNone(
            require_shared_secret(_request(query="token=correct"), "correct")
        )


if __name__ == "__main__":
    unittest.main()
