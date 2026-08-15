"""Permanent regression guard for WhatsApp 2 database migration."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WhatsAppDatabaseRegressionTests(unittest.TestCase):
    def test_router_routes_table_access_through_core(self):
        source = (ROOT / "whatsapp.py").read_text(encoding="utf-8")

        self.assertIn(
            "from core.database import delete_rows, get_rows, patch_rows, post_rows",
            source,
        )
        self.assertIn("return await get_rows(table, params, timeout=15)", source)
        self.assertIn("return await post_rows(table, body, prefer=prefer, timeout=15)", source)
        self.assertIn("return await patch_rows(", source)
        self.assertIn("await delete_rows(table, params, timeout=15)", source)
        self.assertIn("data = await get_rows(table, params, timeout=25)", source)
        self.assertNotIn('f"{SUPABASE_URL}/rest/v1/{table}"', source)
        self.assertNotIn("service_headers", source)
        self.assertNotIn("def _sb_headers()", source)
        self.assertIn("GRAPH_API", source)
        compile(source, "whatsapp.py", "exec")


if __name__ == "__main__":
    unittest.main()
