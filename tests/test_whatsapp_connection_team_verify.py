from pathlib import Path
import unittest

from scripts.refactor_whatsapp_connection_team_verify_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "routers" / "whatsapp_connection.py"


class WhatsAppConnectionTeamVerifyTests(unittest.TestCase):
    def test_transform_uses_same_visible_user_scope_as_number_management(self):
        source = TARGET.read_text(encoding="utf-8")
        transformed = transform_source(source)
        start = transformed.index("async def wa2_numero_verificar")
        end = transformed.index('@router.get("/numeros")', start)
        block = transformed[start:end]
        self.assertIn("ids = await _ids_visibles(user_id)", block)
        self.assertIn('"user_id": _in_filter(ids)', block)
        self.assertNotIn('"user_id": f"eq.{user_id}"', block)
        compile(transformed, "routers/whatsapp_connection.py", "exec")

    def test_transform_is_idempotent(self):
        source = TARGET.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
