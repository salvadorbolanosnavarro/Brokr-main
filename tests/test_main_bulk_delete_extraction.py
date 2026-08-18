from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "bulk_delete.py"


class BulkDeleteExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_routes_live_only_in_router(self):
        self.assertIn('@router.post("/propiedades/eliminar-masivo")', self.router)
        self.assertIn('@router.post("/contactos/eliminar-masivo")', self.router)
        self.assertNotIn('@app.post("/propiedades/eliminar-masivo")', self.main)
        self.assertNotIn('@app.post("/contactos/eliminar-masivo")', self.main)
        self.assertIn('from routers.bulk_delete import router as bulk_delete_router', self.main)
        self.assertIn('app.include_router(bulk_delete_router)', self.main)

    def test_organization_scope_and_permissions_are_preserved(self):
        r = self.router
        self.assertIn('ctx = await get_org_context(user_id)', r)
        self.assertIn('ctx.get("rol_org") in ("owner", "admin")', r)
        self.assertIn('(ctx.get("org_tipo") or "personal") == "empresa"', r)
        self.assertIn('if es_empresa and not es_admin:', r)
        self.assertIn('raise HTTPException(status_code=403, detail=_MSG_SIN_PERMISO)', r)

    def test_property_delete_preserves_batch_and_storage_contract(self):
        r = self.router
        self.assertIn('if not todos and len(ids) > 2000:', r)
        self.assertIn('for i in range(0, len(ids), 200):', r)
        self.assertIn('await delete_rows(', r)
        self.assertIn('"propiedades"', r)
        self.assertIn('accepted_statuses=(200, 204)', r)
        self.assertIn('asyncio.create_task(_borrar_fotos_storage(nombres))', r)
        self.assertIn('for i in range(0, len(nombres), 100):', r)
        self.assertIn('if r.status_code in (200, 204):', r)

    def test_contact_delete_preserves_batch_contract(self):
        r = self.router
        self.assertIn('"contactos"', r)
        self.assertIn('detail="No se pudo leer el directorio."', r)
        self.assertIn('detail="No se pudieron borrar todos los contactos."', r)
        self.assertIn('return {"eliminados": eliminados, "alcance": alcance}', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/bulk_delete.py", "exec")


if __name__ == "__main__":
    unittest.main()
