from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
CONFIG = ROOT / "core" / "config.py"


class WhatsAppAICostGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WHATSAPP.read_text(encoding="utf-8")
        cls.config = CONFIG.read_text(encoding="utf-8")

    def test_global_ai_limit_is_positive_and_has_safe_default(self):
        self.assertIn('wa2_ai_limit=_env_positive_int("WA2_TOPE_IA", 25)', self.config)
        self.assertIn("WA2_TOPE_IA = settings.wa2_ai_limit", self.source)

    def test_zero_or_overlarge_training_limit_falls_back_to_hard_limit(self):
        self.assertIn('max_msj = entren.get("max_mensajes_ia") or 0', self.source)
        self.assertIn("if max_msj <= 0 or max_msj > WA2_TOPE_IA:", self.source)
        self.assertIn("max_msj = WA2_TOPE_IA", self.source)
        self.assertIn("if len(conteo) >= max_msj:", self.source)

    def test_limit_counts_only_ai_sent_messages_for_the_conversation(self):
        self.assertIn('"sender": "eq.ia"', self.source)
        self.assertIn('"conversacion_id": f"eq.{item[\'conversacion_id\']}"', self.source)


if __name__ == "__main__":
    unittest.main()
