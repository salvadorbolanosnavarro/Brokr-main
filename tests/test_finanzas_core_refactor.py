"""Dry-run the first Finanzas Core migration against current source."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_finanzas_core import transform

ROOT = Path(__file__).resolve().parents[1]


class FinanzasCoreRefactorTests(unittest.TestCase):
    def test_transform_matches_current_source_and_compiles(self):
        source = (ROOT / "routers" / "finanzas.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn("from core.auth import require_user_id", updated)
        self.assertIn("from core.config import settings", updated)
        self.assertIn("from core.database import delete_rows, get_rows, patch_rows, post_rows, service_headers", updated)
        self.assertNotIn("os.getenv", updated)
        self.assertNotIn("SUPABASE_SERVICE_KEY = os.getenv", updated)
        self.assertNotIn("async def get_user_id_from_token", updated)
        self.assertIn('return await require_user_id(request, detail="Inicia sesión para continuar.")', updated)
        self.assertIn("ANTHROPIC_API_KEY = settings.anthropic_api_key", updated)
        # Storage and PDF rendering intentionally remain for later isolated cuts.
        self.assertIn("/storage/v1/object/", updated)
        self.assertIn("_PDF_TOKENS = {", updated)
        compile(updated, "routers/finanzas.py", "exec")


if __name__ == "__main__":
    unittest.main()
