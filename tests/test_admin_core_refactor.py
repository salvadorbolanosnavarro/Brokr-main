"""Dry-run the exact Admin Console Core migration against current source."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_admin_core import transform


ROOT = Path(__file__).resolve().parents[1]


class AdminCoreRefactorTests(unittest.TestCase):
    def test_transform_matches_current_source_and_compiles(self):
        source = (ROOT / "admin_consola.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn("from core.admin import require_admin", updated)
        self.assertIn("from core.config import settings", updated)
        self.assertNotIn("import os\n", updated)
        self.assertNotIn("os.getenv", updated)
        self.assertNotIn("SUPABASE_SERVICE_KEY = os.getenv", updated)
        self.assertNotIn("async def _user_id_desde_token", updated)
        self.assertEqual(updated.count("async def require_admin("), 0)
        self.assertIn("CORREO_WEBHOOK_TOKEN = settings.correo_webhook_token", updated)
        compile(updated, "admin_consola.py", "exec")


if __name__ == "__main__":
    unittest.main()
