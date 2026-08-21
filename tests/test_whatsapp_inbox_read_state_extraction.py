from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_inbox_read_state_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
ROUTER = ROOT / "routers" / "whatsapp_inbox_read_state.py"


class WhatsAppInboxReadStateExtractionTests(unittest.TestCase):
    def test_read_state_keeps_tenant_scope_and_blue_tick_contract(self):
        source = ROUTER.read_text(encoding="utf-8")
        for required in (
            '@router.post("/conversaciones/{conversacion_id}/lectura")',
            '"user_id": _in_filter(ids)',
            '"no_leida": True',
            '"unread_count": max(1, int(conv.get("unread_count") or 0))',
            '"unread_count": 0',
            "last_inbound_wamid",
            "escribiendo=False",
        ):
            self.assertIn(required, source)

    def test_transform_moves_only_read_state(self):
        transformed = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertNotIn("class LecturaReq", transformed)
        self.assertNotIn("async def wa2_lectura", transformed)
        self.assertIn("class ConvPatchReq", transformed)
        self.assertIn("async def wa2_conversacion_patch", transformed)
        self.assertIn("async def wa2_borrar_mensaje", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
