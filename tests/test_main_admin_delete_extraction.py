from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "admin_delete.py"


class AdminDeleteExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_destructive_route_is_isolated_from_main(self):
        self.assertIn('@router.post("/admin/user/eliminar")', self.router)
        self.assertNotIn('@app.post("/admin/user/eliminar")', self.main)
        self.assertIn('app.include_router(admin_delete_router)', self.main)
        self.assertIn('@app.get("/admin/user/{user_id}/uso")', self.main)

    def test_all_historical_safety_checks_are_preserved(self):
        r = self.router
        self.assertIn('caller_id = await require_legacy_admin(request)', r)
        self.assertIn('if target_id == caller_id:', r)
        self.assertIn('No puedes eliminar tu propia cuenta de admin.', r)
        self.assertIn('(objetivo.get("rol") or "agente") == "admin"', r)
        self.assertIn('No se puede eliminar a un admin. Primero cámbiale el rol a agente.', r)
        self.assertIn('(req.email_confirmacion or "").strip().lower() != email_real', r)
        self.assertIn('El correo de confirmación no coincide con el de la cuenta.', r)

    def test_rpc_and_storage_order_are_preserved(self):
        r = self.router
        self.assertLess(r.index('rutas_fotos = await _storage_rutas_fotos_de_usuario(target_id)'), r.index('resultado = await call_service_rpc('))
        self.assertIn('"admin_eliminar_usuario_total"', r)
        self.assertIn('{"p_user_id": target_id}', r)
        self.assertIn('timeout=60', r)
        self.assertIn('accepted_statuses=(200,)', r)
        self.assertLess(r.index('resultado = await call_service_rpc('), r.index('archivos_borrados = await _storage_borrar_carpeta_usuario'))
        self.assertIn('return -1 if hubo_error else total', r)

    def test_storage_cleanup_contract_is_preserved(self):
        r = self.router
        self.assertIn('f"{SUPABASE_URL}/storage/v1/object/public/"', r)
        self.assertIn('"select": "fotos"', r)
        self.assertIn('"limit": "10000"', r)
        self.assertIn('for i in range(0, len(rutas), 100):', r)
        self.assertIn('"DELETE"', r)
        self.assertIn('json={"prefixes": rutas[i:i + 100]}', r)
        self.assertIn('while pendientes and pasos < 500:', r)
        self.assertIn('json={"prefix": prefijo, "limit": 100, "offset": offset}', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/admin_delete.py", "exec")


if __name__ == "__main__":
    unittest.main()
