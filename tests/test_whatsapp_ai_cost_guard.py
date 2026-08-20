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

    def test_reaching_limit_hands_chat_to_human_instead_of_silent_drop(self):
        marker = "if len(conteo) >= max_msj:"
        branch = self.source.split(marker, 1)[1].split("# Ya se decidió que la IA sí va a contestar", 1)[0]
        self.assertIn('{"ai_enabled": False, "ia_modo": "off"}', branch)
        self.assertIn('await enviar_push(user_id, "Un prospecto te está esperando"', branch)
        self.assertIn('datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]}', branch)
        self.assertIn("return", branch)


if __name__ == "__main__":
    unittest.main()
