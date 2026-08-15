"""Regression tests for APNs configuration centralized in Core."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from core.config import Settings


class PushConfigTests(unittest.TestCase):
    def test_apns_defaults_preserve_production_behavior(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.apns_bundle_id, "com.broquer.app")
        self.assertEqual(settings.apns_env, "prod")
        self.assertEqual(settings.apns_key_p8, "")

    def test_apns_key_restores_escaped_newlines(self):
        env = {
            "APNS_KEY_P8": "-----BEGIN PRIVATE KEY-----\\nABC\\n-----END PRIVATE KEY-----",
            "APNS_KEY_ID": "ABCDEFGHIJ",
            "APNS_TEAM_ID": "TEAMID1234",
            "APNS_ENV": "sandbox",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()
        self.assertIn("\nABC\n", settings.apns_key_p8)
        self.assertEqual(settings.apns_key_id, "ABCDEFGHIJ")
        self.assertEqual(settings.apns_team_id, "TEAMID1234")
        self.assertEqual(settings.apns_env, "sandbox")


if __name__ == "__main__":
    unittest.main()
