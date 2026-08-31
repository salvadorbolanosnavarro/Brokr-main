"""Regression tests for costly-endpoint access configuration."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from core.config import Settings


class CostlyEndpointConfigTests(unittest.TestCase):
    def test_secure_default_requires_session(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()
        self.assertTrue(settings.ai_require_session)
        self.assertEqual(settings.hourly_anonymous_limit, 40)
        self.assertEqual(settings.hourly_user_limit, 400)

    def test_session_gate_accepts_supported_true_values(self):
        for value in ("1", "true", "TRUE", "si", "sí", "on"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"EXIGIR_SESION_IA": value}, clear=True):
                    settings = Settings.from_env()
                self.assertTrue(settings.ai_require_session)

    def test_session_gate_can_be_explicitly_disabled_for_legacy_operation(self):
        with patch.dict(os.environ, {"EXIGIR_SESION_IA": "false"}, clear=True):
            settings = Settings.from_env()
        self.assertFalse(settings.ai_require_session)

    def test_invalid_or_non_positive_limits_fall_back_safely(self):
        env = {
            "TOPE_HORA_ANONIMO": "no-es-numero",
            "TOPE_HORA_USUARIO": "0",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.hourly_anonymous_limit, 40)
        self.assertEqual(settings.hourly_user_limit, 1)


if __name__ == "__main__":
    unittest.main()
