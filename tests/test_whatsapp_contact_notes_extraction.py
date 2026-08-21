from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_contact_notes_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
ROUTER = ROOT / "routers" / "whatsapp_contact_notes.py"


class WhatsAppContactNotesExtractionTests(unittest.TestCase):
    def test_notes_preserve_tenant_and_crm_mirror(self):
        source = ROUTER.read_text(encoding="utf-8")
        for required in (
            '@router.post("/contactos/{contacto_id}/notas")',
            '"user_id": _in_filter(ids)',
            '"autor": "agente"',
            '"notas": notas',
            "await _sincronizar_contacto_crm(user_id, rows[0], {\"nota\": req.texto})",
        ):
            self.assertIn(required, source)

    def test_transform_moves_only_notes(self):
        transformed = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertNotIn("class NotaReq", transformed)
        self.assertNotIn("async def wa2_agregar_nota", transformed)
        self.assertIn("async def wa2_contacto_patch", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
