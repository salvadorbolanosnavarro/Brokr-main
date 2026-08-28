"""Permanent guards for /easybroker/import-all existing-properties Core read."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "easybroker_migration.py"


class MainEasyBrokerExistingPropertiesReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.legacy_owned = '@app.post("/easybroker/import-all")' in cls.source
        if cls.legacy_owned:
            start = cls.source.index('@app.post("/easybroker/import-all")')
            end = cls.source.index(
                '\n\n# ════════════════════════════════════════════════════════════════\n# Contactos / Importar desde EasyBroker',
                start,
            )
            cls.block = cls.source[start:end]
        else:
            start = cls.router.index('@import_all_router.post("/easybroker/import-all")')
            end = cls.router.index("\n    return import_all_router", start)
            cls.block = cls.router[start:end]

    def test_owner_compiles_and_direct_existing_properties_get_is_gone(self):
        self.assertNotIn('/rest/v1/propiedades', self.block)
        compile(self.source, "main.py", "exec")
        compile(self.router, "routers/easybroker_migration.py", "exec")

    def test_core_read_preserves_fallback_log_and_core_upsert_write(self):
        block = self.block
        if self.legacy_owned:
            self.assertIn('filas_existentes = await get_rows(\n                "propiedades",', block)
            self.assertIn('except httpx.HTTPStatusError:\n            filas_existentes = []', block)
            self.assertIn('await upsert_rows(\n                        "propiedades",', block)
        else:
            self.assertIn('filas_existentes = await get_rows_dep(\n                    "propiedades",', block)
            self.assertIn('except httpx_dep.HTTPStatusError:\n                filas_existentes = []', block)
            self.assertIn('await upsert_rows_dep(\n                            "propiedades",', block)
        self.assertIn('"user_id": f"eq.{user_id}"', block)
        self.assertIn('"eb_public_id": "not.is.null"', block)
        self.assertIn('"select": "eb_public_id,notas,estatus"', block)
        self.assertIn('timeout=15', block)
        self.assertIn('print(f"[import-all] Error leyendo existentes: {e}")', block)
        self.assertIn('conflict="org_id,eb_public_id"', block)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertNotIn('ri = await client.post(', block)


if __name__ == "__main__":
    unittest.main()
