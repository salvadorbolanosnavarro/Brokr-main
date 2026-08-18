"""Permanent guards for background/pending photo Core database routing."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "easybroker_photo_status.py"


class MainPhotoStatusReadsCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        start = cls.router.index("async def _migrar_fotos_org(org_id: str):")
        end = cls.router.index('\n\n@router.get("/easybroker/fotos-pendientes")', start)
        cls.worker = cls.router[start:end]

    def test_main_compiles_and_photo_routes_are_gone(self):
        self.assertNotIn('@app.get("/easybroker/fotos-pendientes")', self.main)
        self.assertNotIn('@app.post("/easybroker/migrar-fotos")', self.main)
        self.assertNotIn('async def _migrar_fotos_org(', self.main)
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/easybroker_photo_status.py", "exec")

    def test_worker_read_and_patch_stay_on_core(self):
        block = self.worker
        self.assertIn('filas = await get_rows("propiedades", params, timeout=30.0)', block)
        self.assertIn('except Exception:\n                    break', block)
        self.assertIn('await patch_rows(', block)
        self.assertIn('{"id": f"eq.{fila.get(\'id\')}"}', block)
        self.assertIn('{"fotos": nuevas}', block)
        self.assertIn('timeout=30.0', block)
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertIn('total_props += 1', block)
        self.assertIn('total_fotos += subidas', block)
        self.assertNotIn('/rest/v1/propiedades', block)

    def test_pending_status_read_stays_on_core_in_router(self):
        block = self.router
        self.assertIn('filas_pendientes = await get_rows(', block)
        self.assertIn('"propiedades"', block)
        self.assertIn('{"org_id": f"eq.{org_id}", "select": "fotos"}', block)
        self.assertIn('timeout=30', block)
        self.assertIn('except Exception:\n        pass', block)
        self.assertNotIn('/rest/v1/propiedades', block)


if __name__ == "__main__":
    unittest.main()
