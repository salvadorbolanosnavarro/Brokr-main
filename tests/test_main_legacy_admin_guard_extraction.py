from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "legacy_admin.py"


class LegacyAdminGuardExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")

    def test_main_delegates_legacy_admin_guard_to_core(self):
        self.assertNotIn('async def require_admin(', self.main)
        self.assertIn('from core.legacy_admin import require_legacy_admin as require_admin', self.main)
        self.assertEqual(self.main.count('require_admin('), 6)

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


if __name__ == "__main__":
    unittest.main()
