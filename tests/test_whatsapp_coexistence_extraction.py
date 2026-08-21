from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_coexistence_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
MODULE = ROOT / "routers" / "whatsapp_coexistence.py"


class WhatsAppCoexistenceExtractionTests(unittest.TestCase):
    def test_service_preserves_echo_agenda_and_history_semantics(self):
        source = MODULE.read_text(encoding="utf-8")
        for required in (
            'val.get("message_echoes")',
            'wa_dest = solo_digitos(eco.get("to") or "")',
            '"Tú · Broq"',
            'ia_default=False',
            'await pausar_por_respuesta_manual(conv_eco, numero, entren_eco)',
            '"conocido": True',
            'val.get("state_sync")',
            'sync.get("type") != "contact"',
            'if not (contacto.get("nombre_chat") or "").strip():',
            'val.get("history")',
            'conocido=True',
        ):
            self.assertIn(required, source)

    def test_transform_replaces_only_coexistence_block(self):
        transformed = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertIn("await _procesar_coexistencia(val, numero)", transformed)
        self.assertIn('for msg in val.get("messages", []):', transformed)
        self.assertNotIn('for eco in (val.get("message_echoes") or []):', transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
