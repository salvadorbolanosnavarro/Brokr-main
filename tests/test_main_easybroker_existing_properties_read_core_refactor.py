"""Permanent guards for /easybroker/import-all existing-properties Core read."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainEasyBrokerExistingPropertiesReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.post("/easybroker/import-all")')
        end = cls.source.index('\n\n@app.post("/contactos/importar-eb")', start)
        cls.block = cls.source[start:end]

    def test_main_compiles_and_direct_existing_properties_get_is_gone(self):
        self.assertNotIn('r = await client.get(\n                f"{SUPABASE_URL}/rest/v1/propiedades"', self.block)
        compile(self.source, "main.py", "exec")

    def test_core_read_preserves_fallback_log_and_core_upsert_write(self):
        block = self.block
        self.assertIn('filas_existentes = await get_rows(\n                "propiedades",', block)
        self.assertIn('"user_id": f"eq.{user_id}"', block)
        self.assertIn('"eb_public_id": "not.is.null"', block)
        self.assertIn('"select": "eb_public_id,notas,estatus"', block)
        self.assertIn('timeout=15', block)
        self.assertIn('except httpx.HTTPStatusError:\n            filas_existentes = []', block)
        self.assertIn('except Exception as e:\n        print(f"[import-all] Error leyendo existentes: {e}")', block)
        self.assertIn('await upsert_rows(\n                        "propiedades",', block)
        self.assertIn('conflict="org_id,eb_public_id"', block)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertNotIn('ri = await client.post(\n                        f"{SUPABASE_URL}/rest/v1/propiedades"', block)


if __name__ == "__main__":
    unittest.main()
