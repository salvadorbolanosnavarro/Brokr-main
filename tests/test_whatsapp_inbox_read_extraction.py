from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_inbox_read_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
INBOX = ROOT / "routers" / "whatsapp_inbox_read.py"


class WhatsAppInboxReadContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = INBOX.read_text(encoding="utf-8")

    def test_conversation_list_is_tenant_scoped_and_bounded(self):
        self.assertIn('"user_id": _in_filter(ids)', self.source)
        self.assertIn('"order": "last_message_at.desc", "limit": "200"', self.source)
        self.assertIn('"order": "created_at.desc", "limit": "1000"', self.source)
        self.assertIn('c["preview_texto"] = (ult.get("body") or "")[:120]', self.source)

    def test_message_pagination_contract_is_preserved(self):
        for snippet in (
            'limit = max(1, min(int(limit or 30), 100))',
            '"created_at": f"gt.{after}"',
            '"order": "created_at.asc", "limit": "200"',
            '"order": "created_at.desc", "limit": str(limit + 1)',
            'params["created_at"] = f"lt.{before}"',
            'rows.reverse()',
            '"incremental": True',
            '"incremental": False',
        ):
            self.assertIn(snippet, self.source)

    def test_read_endpoints_have_no_mutating_database_calls(self):
        self.assertNotIn("sb_post(", self.source)
        self.assertNotIn("sb_patch(", self.source)
        self.assertNotIn("sb_delete(", self.source)


class WhatsAppInboxReadExtractionTests(unittest.TestCase):
    def test_transform_moves_only_read_endpoints(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertIn("from routers.whatsapp_inbox_read import router as whatsapp_inbox_read_router", transformed)
        self.assertIn("router.include_router(whatsapp_inbox_read_router)", transformed)
        self.assertNotIn("async def wa2_conversaciones_list", transformed)
        self.assertNotIn("async def wa2_mensajes_list", transformed)
        self.assertIn("async def wa2_enviar_manual", transformed)
        self.assertIn("async def wa2_lectura", transformed)
        self.assertIn("async def wa2_conversacion_patch", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
