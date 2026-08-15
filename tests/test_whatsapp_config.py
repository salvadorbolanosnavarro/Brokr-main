"""Regression tests for WhatsApp 2 runtime configuration."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from core.config import Settings


class WhatsAppConfigTests(unittest.TestCase):
    def test_whatsapp2_defaults_match_legacy_router(self):
        with patch.dict(os.environ, {}, clear=True):
            s = Settings.from_env()
        self.assertEqual(s.wa2_model, "claude-sonnet-4-6")
        self.assertEqual(s.wa2_meta_app_id, "1709238933850389")
        self.assertEqual(s.wa2_verify_token, "broquer2_verify")
        self.assertEqual(s.wa2_register_pin, "142857")
        self.assertEqual(s.wa2_webhook_url, "https://api.broquer.app/whatsapp2/webhook")
        self.assertEqual(s.wa2_broquer_api_base, "https://api.broquer.app")
        self.assertEqual(s.wa2_zone_default, "America/Mexico_City")
        self.assertEqual(s.wa2_debounce_seconds, 8)
        self.assertEqual(s.wa2_campaign_limit, 250)
        self.assertEqual(s.wa2_media_bucket, "wa-media")
        self.assertEqual(s.wa2_ai_limit, 25)

    def test_whatsapp2_app_secret_preserves_legacy_fallback(self):
        with patch.dict(
            os.environ,
            {"META_APP_SECRET": "meta-secret", "WA_APP_SECRET": ""},
            clear=True,
        ):
            s = Settings.from_env()
        self.assertEqual(s.wa2_meta_app_secret, "meta-secret")
        self.assertEqual(s.wa2_app_secret, "meta-secret")

    def test_whatsapp2_explicit_wa_app_secret_wins_for_webhook_signature(self):
        with patch.dict(
            os.environ,
            {"META_APP_SECRET": "meta-secret", "WA_APP_SECRET": "wa-secret"},
            clear=True,
        ):
            s = Settings.from_env()
        self.assertEqual(s.wa2_meta_app_secret, "meta-secret")
        self.assertEqual(s.wa2_app_secret, "wa-secret")

    def test_whatsapp2_limits_use_safe_legacy_bounds(self):
        with patch.dict(
            os.environ,
            {
                "WA2_DEBOUNCE_SEG": "-4",
                "WA2_CAMPANA_TOPE": "0",
                "WA2_TOPE_IA": "bad",
            },
            clear=True,
        ):
            s = Settings.from_env()
        self.assertEqual(s.wa2_debounce_seconds, 0)
        self.assertEqual(s.wa2_campaign_limit, 1)
        self.assertEqual(s.wa2_ai_limit, 25)


if __name__ == "__main__":
    unittest.main()
