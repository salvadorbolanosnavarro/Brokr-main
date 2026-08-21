from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_contacts_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
MODULE = ROOT / "routers" / "whatsapp_contacts.py"


class WhatsAppContactsExtractionTests(unittest.TestCase):
    def test_contact_service_preserves_known_contact_and_legacy_fallbacks(self):
        source = MODULE.read_text(encoding="utf-8")
        for required in (
            '"conocido": bool(conocido)',
            "nombre_agenda or (nombre or \"\").strip() or None",
            "await crear_contacto_crm(user_id, wa_id, display) if crear_crm else None",
            '"ia_modo": "auto" if ia_default else "off"',
            '"ia_sesion_nueva": bool(ia_default)',
            'fila.pop("ia_modo", None)',
            'fila.pop("ia_sesion_nueva", None)',
        ):
            self.assertIn(required, source)

    def test_transform_keeps_webhook_callers(self):
        transformed = transform_source(TARGET.read_text(encoding="utf-8"))
        for forbidden in (
            "async def _get_numero",
            "async def _agenda_upsert",
            "async def _get_o_crea_contacto",
            "async def _get_o_crea_conversacion",
        ):
            self.assertNotIn(forbidden, transformed)
        self.assertIn("numero = await _get_numero(phone_number_id)", transformed)
        self.assertIn("await _get_o_crea_contacto(", transformed)
        self.assertIn("await _get_o_crea_conversacion(", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
