from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_webhook_messages_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
MODULE = ROOT / "routers" / "whatsapp_webhook_messages.py"


class WhatsAppWebhookMessagesExtractionTests(unittest.TestCase):
    def test_materializer_preserves_message_types_and_fallbacks(self):
        source = MODULE.read_text(encoding="utf-8")
        for required in (
            'tipo_msg == "text"',
            'tipo_msg in ("audio", "voice")',
            'media_sufijo = "nota-de-voz"',
            '"[nota de voz que no se pudo transcribir]"',
            'tipo_msg == "image"',
            '"[foto que no se pudo leer]"',
            'tipo_msg == "location"',
            'tipo_msg == "document"',
            'r"[^A-Za-z0-9._-]"',
            'tipo_msg == "video"',
            'tipo_msg == "contacts"',
            'tipo_msg in ("button", "interactive")',
            '"[respuesta a un botón]"',
            '"[mensaje de tipo {tipo_msg or \'desconocido\'}]"',
            'numero.get("user_id") or ""',
        ):
            self.assertIn(required, source)

    def test_transform_replaces_only_inner_materialization_block(self):
        transformed = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertIn("await _materializar_mensaje(", transformed)
        self.assertIn("es_asesor = _es_asesor(numero, wa_id)", transformed)
        self.assertIn("await _guardar_mensaje(", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
