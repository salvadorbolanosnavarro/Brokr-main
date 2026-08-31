"""Permanent regression guard for the migrated Organizaciones infrastructure."""
from __future__ import annotations

import asyncio
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OrganizacionesCoreRegressionTests(unittest.TestCase):
    def test_router_uses_core_infrastructure_and_keeps_public_exports(self):
        source = (ROOT / "routers" / "organizaciones.py").read_text(encoding="utf-8")

        self.assertIn("from core.auth import get_user_id_from_token", source)
        self.assertIn("from core.config import settings", source)
        self.assertIn("from core.database import delete_rows, get_rows, patch_rows, post_rows", source)
        self.assertNotIn("import os\n", source)
        self.assertNotIn("os.getenv", source)
        self.assertNotIn("def _headers(", source)
        self.assertEqual(source.count("async def get_user_id_from_token("), 0)
        self.assertIn("SUPABASE_URL = settings.supabase_url", source)
        self.assertIn("SUPABASE_SERVICE_KEY = settings.supabase_service_key", source)
        self.assertIn("PERMISOS_VALIDOS = set(VALID_PERMISSIONS)", source)
        self.assertIn("ROLES_ORG_VALIDOS = set(VALID_ORG_ROLES)", source)
        self.assertIn("async def get_org_context", source)
        self.assertIn("def permiso_efectivo", source)
        self.assertIn("async def exigir_gestion_integraciones", source)
        compile(source, "routers/organizaciones.py", "exec")

    def test_context_guard_resolves_core_configuration_aliases(self):
        # A non-empty user id forces the legacy preflight guard to resolve the
        # compatibility aliases. This catches the NameError that a compile-only
        # dry-run cannot detect.
        from routers import organizaciones

        result = asyncio.run(organizaciones.get_org_context("ci-probe-user"))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
