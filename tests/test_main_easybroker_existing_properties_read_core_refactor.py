"""Dry-run guards for /easybroker/import-all existing-properties Core read."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_easybroker_existing_properties_read_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("easybroker_existing_properties_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainEasyBrokerExistingPropertiesReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self, source: str) -> str:
        start = source.index('@app.post("/easybroker/import-all")')
        end = source.index('\n\n@app.post("/contactos/importar-eb")', start)
        return source[start:end]

    def test_transform_compiles_and_removes_only_existing_properties_get(self):
        transformed = _load_transform()(self.source)
        block = self._block(transformed)
        self.assertNotIn('r = await client.get(\n                f"{SUPABASE_URL}/rest/v1/propiedades"', block)
        compile(transformed, "main.py", "exec")

    def test_core_read_preserves_fallback_log_and_upsert_write(self):
        block = self._block(_load_transform()(self.source))
        self.assertIn('filas_existentes = await get_rows(\n                "propiedades",', block)
        self.assertIn('"user_id": f"eq.{user_id}"', block)
        self.assertIn('"eb_public_id": "not.is.null"', block)
        self.assertIn('"select": "eb_public_id,notas,estatus"', block)
        self.assertIn('timeout=15', block)
        self.assertIn('except httpx.HTTPStatusError:\n            filas_existentes = []', block)
        self.assertIn('except Exception as e:\n        print(f"[import-all] Error leyendo existentes: {e}")', block)
        self.assertIn('ri = await client.post(\n                        f"{SUPABASE_URL}/rest/v1/propiedades"', block)
        self.assertIn('"Prefer": "resolution=merge-duplicates,return=minimal"', block)
        self.assertIn('params={"on_conflict": "org_id,eb_public_id"}', block)


if __name__ == "__main__":
    unittest.main()
