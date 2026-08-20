from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "legacy_admin.py"
ADMIN_READ = ROOT / "routers" / "admin_read.py"
ADMIN_ACCOUNTS = ROOT / "routers" / "admin_accounts.py"
ADMIN_DELETE = ROOT / "routers" / "admin_delete.py"


class LegacyAdminGuardExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")
        cls.admin_read = ADMIN_READ.read_text(encoding="utf-8")
        cls.admin_accounts = ADMIN_ACCOUNTS.read_text(encoding="utf-8")
        cls.admin_delete = ADMIN_DELETE.read_text(encoding="utf-8")

    def test_legacy_admin_guard_has_no_local_definition(self):
        self.assertNotIn('async def require_admin(', self.main)
        self.assertIn('from core.legacy_admin import require_legacy_admin as require_admin', self.main)
        self.assertEqual(self.main.count('require_admin('), 1)
        self.assertEqual(self.admin_read.count('require_legacy_admin('), 2)
        self.assertEqual(self.admin_accounts.count('require_legacy_admin('), 2)
        self.assertEqual(self.admin_delete.count('require_legacy_admin('), 1)

    def test_exact_legacy_401_403_contract_is_preserved(self):
        c = self.core
        self.assertIn('user_id = await get_user_id_from_token(request)', c)
        self.assertIn('raise HTTPException(status_code=401, detail="No autenticado.")', c)
        self.assertIn('rol = await get_user_rol(user_id)', c)
        self.assertIn('if rol != "admin":', c)
        self.assertIn('raise HTTPException(status_code=403, detail="Acceso denegado.")', c)
        self.assertNotIn('from core.admin import', c)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.core, "core/legacy_admin.py", "exec")
        compile(self.admin_read, "routers/admin_read.py", "exec")
        compile(self.admin_accounts, "routers/admin_accounts.py", "exec")
        compile(self.admin_delete, "routers/admin_delete.py", "exec")


if __name__ == "__main__":
    unittest.main()
