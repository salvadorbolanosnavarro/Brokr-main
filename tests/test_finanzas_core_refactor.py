"""Permanent regression guard for the first Finanzas Core migration cut."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FinanzasCoreRegressionTests(unittest.TestCase):
    def test_router_uses_core_config_auth_and_database(self):
        source = (ROOT / "routers" / "finanzas.py").read_text(encoding="utf-8")

        self.assertIn("from core.auth import require_user_id", source)
        self.assertIn("from core.config import settings", source)
        self.assertIn("from core.database import delete_rows, get_rows, patch_rows, post_rows, service_headers", source)
        self.assertNotIn("os.getenv", source)
        self.assertNotIn("SUPABASE_SERVICE_KEY = os.getenv", source)
        self.assertNotIn("async def get_user_id_from_token", source)
        self.assertIn('return await require_user_id(request, detail="Inicia sesión para continuar.")', source)
        self.assertIn("ANTHROPIC_API_KEY = settings.anthropic_api_key", source)
        # These are intentionally separate migration cuts and must not be
        # mistaken for completed work yet.
        self.assertIn("/storage/v1/object/", source)
        self.assertIn("_PDF_TOKENS = {", source)
        compile(source, "routers/finanzas.py", "exec")


if __name__ == "__main__":
    unittest.main()
