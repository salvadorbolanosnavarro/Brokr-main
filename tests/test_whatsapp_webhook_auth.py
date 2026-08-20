from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from routers.whatsapp_webhook_auth import meta_verify_response


ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
AUTH = ROOT / "routers" / "whatsapp_webhook_auth.py"
TRANSFORM = ROOT / "scripts" / "refactor_whatsapp_extract_webhook_verify_core.py"


class WhatsAppWebhookAuthTests(unittest.TestCase):
    @staticmethod
    def _request(**params):
        return SimpleNamespace(query_params=params)

    def test_meta_challenge_fails_closed_without_server_token(self):
        r = meta_verify_response(
            self._request(**{"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "x"}),
            "",
        )
        self.assertEqual(r.status_code, 503)

    def test_meta_challenge_rejects_invalid_token(self):
        r = meta_verify_response(
            self._request(**{"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "x"}),
            "secret",
        )
        self.assertEqual(r.status_code, 403)

    def test_meta_challenge_preserves_valid_plain_text_response(self):
        r = meta_verify_response(
            self._request(**{"hub.mode": "subscribe", "hub.verify_token": "secret", "hub.challenge": "12345"}),
            "secret",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.body, b"12345")
        self.assertTrue((r.media_type or "").startswith("text/plain"))

    def test_whatsapp_source_is_valid_before_or_after_security_cut(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        local = (
            'def wa2_verify_webhook(request: Request):' in source
            and 'p.get("hub.verify_token") == WA2_VERIFY_TOKEN' in source
        )
        delegated = "return meta_verify_response(request, WA2_VERIFY_TOKEN)" in source
        self.assertNotEqual(local, delegated)

        # POST message ingestion must remain independently fail-closed.
        self.assertIn("if not WA2_APP_SECRET:", source)
        self.assertIn("return Response(status_code=503)", source)
        self.assertIn("hmac.compare_digest(sig, expected)", source)
        self.assertIn("return Response(status_code=403)", source)

        compile(source, "whatsapp.py", "exec")
        compile(AUTH.read_text(encoding="utf-8"), "routers/whatsapp_webhook_auth.py", "exec")
        compile(TRANSFORM.read_text(encoding="utf-8"), str(TRANSFORM), "exec")


if __name__ == "__main__":
    unittest.main()
