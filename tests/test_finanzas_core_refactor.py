"""Permanent regression guard for migrated Finanzas shared infrastructure."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FinanzasCoreRegressionTests(unittest.TestCase):
    def test_router_uses_core_config_auth_database_and_storage(self):
        source = (ROOT / "routers" / "finanzas.py").read_text(encoding="utf-8")

        self.assertIn("from core.auth import require_user_id", source)
        self.assertIn("from core.config import settings", source)
        self.assertIn("from core.database import delete_rows, get_rows, patch_rows, post_rows", source)
        self.assertIn(
            "from core.storage import create_signed_object_url, delete_object, upload_object",
            source,
        )
        self.assertNotIn("service_headers", source)
        self.assertNotIn("os.getenv", source)
        self.assertNotIn("SUPABASE_SERVICE_KEY = os.getenv", source)
        self.assertNotIn("async def get_user_id_from_token", source)
        self.assertNotIn("/storage/v1/object/", source)
        self.assertIn('return await require_user_id(request, detail="Inicia sesión para continuar.")', source)
        self.assertIn("ANTHROPIC_API_KEY = settings.anthropic_api_key", source)
        # PDF design remains the next isolated migration cut until its own
        # reviewed transform is applied.
        self.assertIn("_PDF_TOKENS = {", source)
        compile(source, "routers/finanzas.py", "exec")


if __name__ == "__main__":
    unittest.main()
