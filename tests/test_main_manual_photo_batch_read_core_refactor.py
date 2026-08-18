"""Permanent guards for /easybroker/migrar-fotos batch Core database routing."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "easybroker_photo_status.py"


class MainManualPhotoBatchReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.source = ROUTER.read_text(encoding="utf-8")
        start = cls.source.index('@router.post("/easybroker/migrar-fotos")')
        cls.block = cls.source[start:]

    def test_main_compiles_and_manual_route_is_extracted(self):
        self.assertNotIn('@app.post("/easybroker/migrar-fotos")', self.main)
        self.assertIn('@router.post("/easybroker/migrar-fotos")', self.block)
        self.assertNotIn('/rest/v1/propiedades', self.block)
        compile(self.main, "main.py", "exec")
        compile(self.source, "routers/easybroker_photo_status.py", "exec")

    def test_core_database_preserves_500_storage_and_patch_contract(self):
        block = self.block
        self.assertIn('filas = await get_rows("propiedades", params, timeout=30)', block)
        self.assertIn('except Exception:\n        raise HTTPException(status_code=500, detail="No se pudo leer el inventario.")', block)
        self.assertIn('f"{SUPABASE_URL}/storage/v1/object/{_FOTOS_BUCKET}/{nombre}"', block)
        self.assertIn('await patch_rows(', block)
        self.assertIn('"propiedades"', block)
        self.assertIn('{"id": f"eq.{pid}"}', block)
        self.assertIn('{"fotos": nuevas}', block)
        self.assertIn('timeout=60', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertIn('propiedades_ok += 1', block)
        self.assertIn('fotos_subidas += subidas_prop', block)
        self.assertIn('except Exception:\n                errores += 1', block)


if __name__ == "__main__":
    unittest.main()
