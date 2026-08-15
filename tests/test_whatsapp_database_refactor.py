"""Permanent regression guard for WhatsApp 2 database migration."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WhatsAppDatabaseRegressionTests(unittest.TestCase):
    def test_router_routes_table_access_through_core_and_keeps_storage_separate(self):
        source = (ROOT / "whatsapp.py").read_text(encoding="utf-8")

        self.assertIn(
            "from core.database import delete_rows, get_rows, patch_rows, post_rows, service_headers",
            source,
        )
        self.assertIn("return service_headers()", source)
        self.assertIn("return await get_rows(table, params, timeout=15)", source)
        self.assertIn("return await post_rows(table, body, prefer=prefer, timeout=15)", source)
        self.assertIn("return await patch_rows(", source)
        self.assertIn("await delete_rows(table, params, timeout=15)", source)
        self.assertIn("data = await get_rows(table, params, timeout=25)", source)
        self.assertNotIn('f"{SUPABASE_URL}/rest/v1/{table}"', source)
        # Storage/media still has its own isolated migration cut.
        self.assertIn("/storage/v1/object/", source)
        self.assertIn("WA_MEDIA_BUCKET", source)
        self.assertIn("GRAPH_API", source)
        compile(source, "whatsapp.py", "exec")


if __name__ == "__main__":
    unittest.main()
