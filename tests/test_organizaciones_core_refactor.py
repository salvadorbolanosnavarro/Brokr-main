"""Dry-run the exact Organizaciones Core migration against current source."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_organizaciones_core import transform

ROOT = Path(__file__).resolve().parents[1]


class OrganizacionesCoreRefactorTests(unittest.TestCase):
    def test_transform_matches_current_source_and_compiles(self):
        source = (ROOT / "routers" / "organizaciones.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn("from core.auth import get_user_id_from_token", updated)
        self.assertIn("from core.config import settings", updated)
        self.assertIn("from core.database import delete_rows, get_rows, patch_rows, post_rows", updated)
        self.assertNotIn("import os\n", updated)
        self.assertNotIn("os.getenv", updated)
        self.assertNotIn("def _headers(", updated)
        self.assertEqual(updated.count("async def get_user_id_from_token("), 0)
        self.assertIn("PERMISOS_VALIDOS = set(VALID_PERMISSIONS)", updated)
        self.assertIn("ROLES_ORG_VALIDOS = set(VALID_ORG_ROLES)", updated)
        self.assertIn("async def get_org_context", updated)
        self.assertIn("def permiso_efectivo", updated)
        self.assertIn("async def exigir_gestion_integraciones", updated)
        compile(updated, "routers/organizaciones.py", "exec")


if __name__ == "__main__":
    unittest.main()
