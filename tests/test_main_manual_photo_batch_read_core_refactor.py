"""Permanent guards for /easybroker/migrar-fotos batch Core database routing."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainManualPhotoBatchReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.post("/easybroker/migrar-fotos")')
        end = cls.source.index('\n\n# ════════════════════════════════════════════════════════════════', start)
        cls.block = cls.source[start:end]

    def test_main_compiles_and_direct_batch_rest_io_is_gone(self):
        self.assertNotIn('r = await client.get(f"{SUPABASE_URL}/rest/v1/propiedades"', self.block)
        self.assertNotIn('await client.patch(\n                    f"{SUPABASE_URL}/rest/v1/propiedades"', self.block)
        compile(self.source, "main.py", "exec")

    def test_core_database_preserves_500_storage_and_patch_contract(self):
        block = self.block
        self.assertIn('filas = await get_rows("propiedades", params, timeout=30)', block)
        self.assertIn('except Exception:\n        raise HTTPException(status_code=500, detail="No se pudo leer el inventario.")', block)
        self.assertIn('ru = await client.post(\n                f"{SUPABASE_URL}/storage/v1/object/{_FOTOS_BUCKET}/{nombre}"', block)
        self.assertIn('await patch_rows(\n                    "propiedades",', block)
        self.assertIn('{"id": f"eq.{pid}"}', block)
        self.assertIn('{"fotos": nuevas}', block)
        self.assertIn('timeout=60', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertIn('propiedades_ok += 1', block)
        self.assertIn('fotos_subidas += subidas_prop', block)
        self.assertIn('except Exception:\n                errores += 1', block)


if __name__ == "__main__":
    unittest.main()
