"""Dry-run the narrow main.py security migration against current source."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_main_security import transform

ROOT = Path(__file__).resolve().parents[1]


class MainSecurityRefactorTests(unittest.TestCase):
    def test_transform_closes_privileged_fallbacks_and_compiles(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn("from core.config import settings", updated)
        self.assertIn("SUPABASE_SERVICE_KEY = settings.supabase_service_key", updated)
        self.assertNotIn(
            'SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "") or SUPABASE_KEY',
            updated,
        )
        self.assertIn("from routers.organizaciones import (", updated)
        self.assertNotIn("No se pudo importar el contexto de organización", updated)
        self.assertNotIn(
            "async def exigir_gestion_integraciones(request):\n        return await get_user_id_from_token(request)",
            updated,
        )
        # Broad main.py env/auth migration is deliberately a later cut.
        self.assertIn('EB_API_KEY       = os.environ.get("EB_API_KEY", "")', updated)
        self.assertIn("async def get_user_id_from_token", updated)
        compile(updated, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
