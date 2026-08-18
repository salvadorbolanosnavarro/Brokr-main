from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "easybroker_photo_status.py"
BULK = ROOT / "routers" / "bulk_delete.py"


class EasyBrokerPhotoMigrationExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.bulk = BULK.read_text(encoding="utf-8")

    def test_migration_domain_lives_in_router(self):
        r = self.router
        self.assertIn('async def _migrar_fotos_org(org_id: str):', r)
        self.assertIn('@router.post("/easybroker/migrar-fotos")', r)
        self.assertIn('def _comprimir_imagen(raw: bytes):', r)
        self.assertIn('async def _foto_a_storage(', r)
        self.assertNotIn('@app.post("/easybroker/migrar-fotos")', self.main)
        self.assertNotIn('async def _migrar_fotos_org(', self.main)

    def test_import_all_keeps_background_worker_contract(self):
        m = self.main
        self.assertIn('from routers.easybroker_photo_status import (_migrar_fotos_org, router as easybroker_photo_status_router)', m)
        self.assertIn('asyncio.create_task(_migrar_fotos_org(org_id_import))', m)
        self.assertIn('fotos_lanzado = True', m)

    def test_batch_migration_contract_stays_intact(self):
        r = self.router
        self.assertIn('CHUNK = 10', r)
        self.assertIn('filas = await get_rows("propiedades", params, timeout=30)', r)
        self.assertIn('lote = fotos[i:i+4]', r)
        self.assertIn('accepted_statuses=(200, 204)', r)
        self.assertIn('"hay_mas": hay_mas', r)
        self.assertIn('detail="No se pudo leer el inventario."', r)

    def test_background_worker_preserves_fail_soft_patch(self):
        r = self.router
        self.assertIn('filas = await get_rows("propiedades", params, timeout=30.0)', r)
        self.assertIn('except httpx.HTTPStatusError:', r)
        self.assertIn('await asyncio.sleep(0.3)', r)
        self.assertIn('_fotos_en_proceso.discard(org_id)', r)

    def test_bulk_delete_uses_same_shared_bucket_after_its_extraction(self):
        self.assertNotIn('@app.post("/propiedades/eliminar-masivo")', self.main)
        self.assertIn('@router.post("/propiedades/eliminar-masivo")', self.bulk)
        self.assertIn('from core.property_photos import FOTOS_BUCKET as _FOTOS_BUCKET', self.bulk)
        self.assertIn('f"{SUPABASE_URL}/storage/v1/object/{_FOTOS_BUCKET}"', self.bulk)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/easybroker_photo_status.py", "exec")
        compile(self.bulk, "routers/bulk_delete.py", "exec")


if __name__ == "__main__":
    unittest.main()
