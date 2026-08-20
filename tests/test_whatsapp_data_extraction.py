"""Regression guards for the first WhatsApp 2 decomposition cut."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
DATA = ROOT / "routers" / "whatsapp_data.py"
SCRIPT = ROOT / "scripts" / "refactor_whatsapp_extract_data_core.py"


class WhatsAppDataExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WHATSAPP.read_text(encoding="utf-8")
        cls.data = DATA.read_text(encoding="utf-8")
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_adapter_policies_are_preserved_in_domain_module(self):
        d = self.data
        self.assertIn("for intento in (1, 2):", d)
        self.assertIn("return await get_rows(table, params, timeout=15)", d)
        self.assertIn("return await post_rows(table, body, prefer=prefer, timeout=15)", d)
        self.assertIn('if r.status_code == 409:', d)
        self.assertIn('log.info("sb_post %s: la fila ya existe (409).", table)', d)
        self.assertIn('prefer="return=representation"', d)
        self.assertIn("await delete_rows(table, params, timeout=15)", d)
        self.assertIn("return False", d)

    def test_transform_is_bounded_to_helper_block(self):
        s = self.script
        self.assertIn("BLOCK_START", s)
        self.assertIn('BLOCK_END = "async def _require_user(request: Request) -> str:', s)
        self.assertIn("compile(transformed, str(SOURCE), \"exec\")", s)
        self.assertNotIn("write_text(self.data", s)

    def test_prepared_module_and_script_compile(self):
        compile(self.data, "routers/whatsapp_data.py", "exec")
        compile(self.script, "scripts/refactor_whatsapp_extract_data_core.py", "exec")


if __name__ == "__main__":
    unittest.main()
