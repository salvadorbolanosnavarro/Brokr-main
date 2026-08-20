from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from routers.whatsapp_policy import _conv_pausada, _ia_decide, _modo_conv, _parse_ts


ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
POLICY = ROOT / "routers" / "whatsapp_policy.py"


class WhatsAppPolicyExtractionTests(unittest.TestCase):
    def test_source_is_valid_before_or_after_bounded_extraction(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        imported = (
            "from routers.whatsapp_policy import _conv_pausada, _ia_decide, _modo_conv, _parse_ts"
            in source
        )
        local = all(
            f"def {name}(" in source
            for name in ("_parse_ts", "_modo_conv", "_conv_pausada", "_ia_decide")
        )
        self.assertNotEqual(imported, local, "WhatsApp policy must have one canonical implementation")
        self.assertIn("async def _pausar_por_respuesta_manual(", source)
        compile(source, "whatsapp.py", "exec")
        compile(POLICY.read_text(encoding="utf-8"), "routers/whatsapp_policy.py", "exec")

    def test_timestamp_parser_preserves_legacy_behavior(self):
        self.assertIsNone(_parse_ts(None))
        self.assertIsNone(_parse_ts("not-a-date"))
        aware = _parse_ts("2026-08-20T12:00:00Z")
        self.assertIsNotNone(aware)
        self.assertIsNotNone(aware.tzinfo)
        naive = _parse_ts("2026-08-20T12:00:00")
        self.assertEqual(naive.tzinfo, timezone.utc)

    def test_legacy_mode_fallback_is_preserved(self):
        self.assertEqual(_modo_conv({"ia_modo": "on"}), "on")
        self.assertEqual(_modo_conv({"ia_modo": "off"}), "off")
        self.assertEqual(_modo_conv({"ia_modo": "auto"}), "auto")
        self.assertEqual(_modo_conv({"ai_enabled": False}), "off")
        self.assertEqual(_modo_conv({}), "auto")

    def test_pause_detection_is_time_aware(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        self.assertTrue(_conv_pausada({"ia_pausada_hasta": future}))
        self.assertFalse(_conv_pausada({"ia_pausada_hasta": past}))
        self.assertFalse(_conv_pausada({}))

    def test_ai_decision_priority_contract(self):
        always = {"modo_ia": "siempre_encendida"}
        number_on = {"ia_enabled": True}

        self.assertFalse(_ia_decide({"ia_modo": "on"}, always, {"ia_enabled": False}))
        self.assertFalse(_ia_decide({"ia_modo": "off"}, always, number_on))

        future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        self.assertFalse(
            _ia_decide({"ia_modo": "on", "ia_pausada_hasta": future}, always, number_on)
        )

        self.assertTrue(
            _ia_decide({"ia_modo": "on"}, {"modo_ia": "siempre_apagada"}, number_on)
        )
        self.assertFalse(
            _ia_decide({"ia_modo": "auto"}, {"modo_ia": "siempre_apagada"}, number_on)
        )
        self.assertTrue(
            _ia_decide(
                {"ia_modo": "auto", "ia_sesion_nueva": True},
                {"modo_ia": "solo_nuevos"},
                number_on,
            )
        )
        self.assertFalse(
            _ia_decide(
                {"ia_modo": "auto", "ia_sesion_nueva": False},
                {"modo_ia": "solo_nuevos"},
                number_on,
            )
        )
        self.assertTrue(_ia_decide({"ia_modo": "auto"}, {}, number_on))


if __name__ == "__main__":
    unittest.main()
