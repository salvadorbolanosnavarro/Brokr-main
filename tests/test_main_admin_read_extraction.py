from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "admin_read.py"


class AdminReadExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_routes_live_only_in_router(self):
        self.assertIn('@router.get("/admin/me")', self.router)
        self.assertIn('@router.get("/admin/users")', self.router)
        self.assertNotIn('@app.get("/admin/me")', self.main)
        self.assertNotIn('@app.get("/admin/users")', self.main)
        self.assertIn('app.include_router(admin_read_router)', self.main)

    def test_legacy_auth_and_read_contracts_are_preserved(self):
        r = self.router
        self.assertGreaterEqual(r.count('await require_legacy_admin(request)'), 2)
        self.assertIn('users = await get_rows(', r)
        self.assertIn('"select": "id,email,nombre,telefono,rol,activo,created_at"', r)
        self.assertIn('"order": "created_at.desc"', r)
        self.assertIn('"limit": "10000"', r)
        self.assertIn('raise HTTPException(status_code=500, detail=f"Error listando usuarios: {exc.response.text}")', r)
        self.assertIn('subs = await get_rows(', r)
        self.assertIn('"select": "user_id,plan_id,plan_nombre,status,updated_at"', r)
        self.assertIn('except httpx.HTTPStatusError:\n        subs = []', r)
        self.assertIn('if uid and uid not in subs_by_user:', r)
        self.assertIn('"sub_active": (sub.get("status") in ("active", "trialing")) if sub else False', r)

    def test_admin_writes_stay_in_main_for_next_cut(self):
        self.assertIn('class AdminRolReq(BaseModel):', self.main)
        self.assertIn('@app.post("/admin/user/rol")', self.main)
        self.assertIn('@app.post("/admin/user/activo")', self.main)
        self.assertIn('@app.post("/admin/user/eliminar")', self.main)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/admin_read.py", "exec")


if __name__ == "__main__":
    unittest.main()
