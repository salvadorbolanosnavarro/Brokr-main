from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "easybroker_photo_status.py"
BULK = ROOT / "routers" / "bulk_delete.py"


class EasyBrokerPhotoStatusExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.bulk = BULK.read_text(encoding="utf-8")

    def test_photo_routes_live_only_in_router(self):
        self.assertIn('@router.get("/easybroker/fotos-pendientes")', self.router)
        self.assertIn('@router.post("/easybroker/migrar-fotos")', self.router)
        self.assertNotIn('@app.get("/easybroker/fotos-pendientes")', self.main)
        self.assertNotIn('@app.post("/easybroker/migrar-fotos")', self.main)
        self.assertIn('router as easybroker_photo_status_router', self.main)
        self.assertIn('app.include_router(easybroker_photo_status_router)', self.main)

    def test_shared_photo_state_is_canonical(self):
        self.assertNotIn('FOTOS_BUCKET as _FOTOS_BUCKET', self.main)
        self.assertNotIn('_FOTOS_BUCKET', self.main)
        self.assertNotIn('foto_migrable as _foto_migrable', self.main)
        self.assertNotIn('fotos_en_proceso as _fotos_en_proceso', self.main)
        self.assertIn('FOTOS_BUCKET as _FOTOS_BUCKET', self.router)
        self.assertIn('foto_migrable as _foto_migrable', self.router)
        self.assertIn('fotos_en_proceso as _fotos_en_proceso', self.router)
        self.assertIn('FOTOS_BUCKET as _FOTOS_BUCKET', self.bulk)
        self.assertNotIn('_fotos_en_proceso = set()', self.main)

    def test_status_contract_is_preserved(self):
        r = self.router
        self.assertIn('raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")', r)
        self.assertIn('return {"pendientes": 0, "en_proceso": False}', r)
        self.assertIn('{"org_id": f"eq.{org_id}", "select": "fotos"}', r)
        self.assertIn('timeout=30', r)
        self.assertIn('org_id in _fotos_en_proceso', r)

    def test_background_worker_is_imported_for_import_all(self):
        self.assertIn('_migrar_fotos_org, router as easybroker_photo_status_router', self.main)
        self.assertIn('asyncio.create_task(_migrar_fotos_org(org_id_import))', self.main)
        self.assertNotIn('async def _migrar_fotos_org(', self.main)
        self.assertIn('async def _migrar_fotos_org(', self.router)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/easybroker_photo_status.py", "exec")
        compile(self.bulk, "routers/bulk_delete.py", "exec")


if __name__ == "__main__":
    unittest.main()
