"""Dry-run WhatsApp 2 database migration against current source."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_whatsapp_database import transform

ROOT = Path(__file__).resolve().parents[1]


class WhatsAppDatabaseRefactorTests(unittest.TestCase):
    def test_transform_routes_table_access_through_core_and_compiles(self):
        source = (ROOT / "whatsapp.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn(
            "from core.database import delete_rows, get_rows, patch_rows, post_rows, service_headers",
            updated,
        )
        self.assertIn("return service_headers()", updated)
        self.assertIn("return await get_rows(table, params, timeout=15)", updated)
        self.assertIn("return await post_rows(table, body, prefer=prefer, timeout=15)", updated)
        self.assertIn("return await patch_rows(", updated)
        self.assertIn("await delete_rows(table, params, timeout=15)", updated)
        self.assertNotIn('f"{SUPABASE_URL}/rest/v1/{table}"', updated)
        # Storage/media and external HTTP integrations are separate concerns.
        self.assertIn("GRAPH_API", updated)
        self.assertIn("WA_MEDIA_BUCKET", updated)
        self.assertIn("async def _require_user", updated)
        compile(updated, "whatsapp.py", "exec")


if __name__ == "__main__":
    unittest.main()
