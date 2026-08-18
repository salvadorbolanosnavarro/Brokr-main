from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "easybroker_photo_status.py"


class EasyBrokerPhotoStatusExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_status_route_lives_only_in_router(self):
        self.assertIn('@router.get("/easybroker/fotos-pendientes")', self.router)
        self.assertNotIn('@app.get("/easybroker/fotos-pendientes")', self.main)
        self.assertIn('from routers.easybroker_photo_status import router as easybroker_photo_status_router', self.main)
        self.assertIn('app.include_router(easybroker_photo_status_router)', self.main)

    def test_main_uses_canonical_shared_photo_state(self):
        self.assertIn('FOTOS_BUCKET as _FOTOS_BUCKET', self.main)
        self.assertIn('foto_migrable as _foto_migrable', self.main)
        self.assertIn('foto_ya_es_de_broquer as _foto_ya_es_de_broquer', self.main)
        self.assertIn('fotos_en_proceso as _fotos_en_proceso', self.main)
        self.assertNotIn('_fotos_en_proceso = set()', self.main)
        self.assertNotIn('def _foto_migrable(', self.main)

    def test_status_contract_is_preserved(self):
        r = self.router
        self.assertIn('raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")', r)
        self.assertIn('return {"pendientes": 0, "en_proceso": False}', r)
        self.assertIn('"propiedades"', r)
        self.assertIn('{"org_id": f"eq.{org_id}", "select": "fotos"}', r)
        self.assertIn('timeout=30', r)
        self.assertIn('except Exception:', r)
        self.assertIn('org_id in fotos_en_proceso', r)

    def test_remaining_photo_migration_stays_in_main_for_next_cut(self):
        self.assertIn('async def _migrar_fotos_org(', self.main)
        self.assertIn('@app.post("/easybroker/migrar-fotos")', self.main)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/easybroker_photo_status.py", "exec")


if __name__ == "__main__":
    unittest.main()
