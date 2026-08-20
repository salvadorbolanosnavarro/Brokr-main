from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "admin_accounts.py"


class AdminAccountsExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_non_destructive_admin_routes_live_only_in_router(self):
        self.assertIn('@router.post("/admin/user/rol")', self.router)
        self.assertIn('@router.post("/admin/user/activo")', self.router)
        self.assertNotIn('@app.post("/admin/user/rol")', self.main)
        self.assertNotIn('@app.post("/admin/user/activo")', self.main)
        self.assertIn('app.include_router(admin_accounts_router)', self.main)

    def test_role_contract_and_self_protection_are_preserved(self):
        r = self.router
        self.assertIn('ROLES_VALIDOS = {"admin", "equipo", "agente"}', r)
        self.assertIn('if target_id == caller_id and req.rol != "admin":', r)
        self.assertIn('No puedes cambiar tu propio rol de admin.', r)
        self.assertIn('await patch_rows_no_response(', r)
        self.assertIn('{"rol": req.rol}', r)
        self.assertIn('accepted_statuses=(200, 204)', r)
        self.assertIn('Error actualizando rol', r)

    def test_active_contract_and_self_protection_are_preserved(self):
        r = self.router
        self.assertIn('if target_id == caller_id and not req.activo:', r)
        self.assertIn('No puedes desactivar tu propia cuenta de admin.', r)
        self.assertIn('{"activo": bool(req.activo)}', r)
        self.assertIn('prefer="return=minimal"', r)
        self.assertIn('timeout=10', r)
        self.assertIn('Error actualizando activo', r)

    def test_destructive_delete_stays_in_main_for_separate_static_cut(self):
        self.assertIn('class AdminEliminarReq(BaseModel):', self.main)
        self.assertIn('@app.post("/admin/user/eliminar")', self.main)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/admin_accounts.py", "exec")


if __name__ == "__main__":
    unittest.main()
