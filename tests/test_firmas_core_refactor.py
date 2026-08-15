"""Dry-run the exact Firmas Core migration against current source."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_firmas_core import transform

ROOT = Path(__file__).resolve().parents[1]


class FirmasCoreRefactorTests(unittest.TestCase):
    def test_transform_matches_current_source_and_compiles(self):
        source = (ROOT / "routers" / "firmas.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn("from core.auth import require_user_id", updated)
        self.assertIn("from core.config import settings", updated)
        self.assertNotIn("import os\n", updated)
        self.assertNotIn("os.getenv", updated)
        self.assertNotIn("SUPABASE_SERVICE_KEY = os.getenv", updated)
        self.assertNotIn("async def get_user_id_from_token", updated)
        self.assertIn("return await require_user_id(", updated)
        self.assertIn("from core.subscriptions import require_paid_feature_access", updated)
        compile(updated, "routers/firmas.py", "exec")


if __name__ == "__main__":
    unittest.main()
