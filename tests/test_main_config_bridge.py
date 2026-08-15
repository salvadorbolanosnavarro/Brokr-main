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


if __name__ == "__main__":
    unittest.main()
