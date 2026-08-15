"""Regression tests for the remaining main.py configuration bridge."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from core.config import Settings


class MainConfigBridgeTests(unittest.TestCase):
    def test_legacy_main_defaults_are_preserved_in_core(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()

        self.assertEqual(settings.easybroker_api_key, "")
        self.assertEqual(settings.apify_api_key, "")
        self.assertEqual(settings.google_places_key, "")
        self.assertEqual(settings.banxico_token, "")
        self.assertEqual(settings.banxico_series_udis, "SP68257")
        self.assertEqual(settings.banxico_series_inpc, "SP74625")
        self.assertEqual(settings.legacy_main_fb_app_id, "")
        self.assertEqual(settings.legacy_main_fb_app_secret, "")
        self.assertEqual(
            settings.legacy_main_frontend_url,
            "https://app.navarroai.com.mx",
        )

    def test_main_environment_values_are_normalized_centrally(self):
        env = {
            "EB_API_KEY": "eb-secret",
            "APIFY_API_KEY": "apify-secret",
            "GOOGLE_PLACES_KEY": "places-secret",
            "BANXICO_TOKEN": '  "banxico-secret"  ',
            "BANXICO_SERIE_UDIS": "udis-custom",
            "BANXICO_SERIE_INPC": "inpc-custom",
            "FRONTEND_URL": "https://example.test/app",
            "FB_APP_ID": "legacy-fb-id",
            "FB_APP_SECRET": "legacy-fb-secret",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()

        self.assertEqual(settings.easybroker_api_key, "eb-secret")
        self.assertEqual(settings.apify_api_key, "apify-secret")
        self.assertEqual(settings.google_places_key, "places-secret")
        self.assertEqual(settings.banxico_token, "banxico-secret")
        self.assertEqual(settings.banxico_series_udis, "udis-custom")
        self.assertEqual(settings.banxico_series_inpc, "inpc-custom")
        self.assertEqual(settings.legacy_main_frontend_url, "https://example.test/app")
        self.assertEqual(settings.legacy_main_fb_app_id, "legacy-fb-id")
        self.assertEqual(settings.legacy_main_fb_app_secret, "legacy-fb-secret")

    def test_publishable_key_is_preferred_over_legacy_anon_key(self):
        env = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_new",
            "SUPABASE_ANON_KEY": "legacy-anon",
            "SUPABASE_KEY": "older-legacy-alias",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()

        self.assertEqual(settings.supabase_anon_key, "sb_publishable_new")

    def test_legacy_anon_remains_temporary_fallback(self):
        env = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_ANON_KEY": "legacy-anon",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()

        self.assertEqual(settings.supabase_anon_key, "legacy-anon")


if __name__ == "__main__":
    unittest.main()
