from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "admin_usage.py"
CORE = ROOT / "core" / "legacy_admin.py"


class AdminUsageExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")

    def test_final_admin_route_lives_only_in_router(self):
        self.assertIn('@router.get("/admin/user/{user_id}/uso")', self.router)
        self.assertNotIn('@app.get("/admin/user/{user_id}/uso")', self.main)
        self.assertNotIn('async def admin_user_uso(', self.main)
        self.assertIn('app.include_router(admin_usage_router)', self.main)
        self.assertNotIn('from core.legacy_admin import require_legacy_admin as require_admin', self.main)

    def test_auth_config_and_range_contracts_are_preserved(self):
        r = self.router
        self.assertIn('await require_legacy_admin(request)', r)
        self.assertIn('if not settings.supabase_url or not settings.supabase_service_key:', r)
        self.assertIn('raise HTTPException(status_code=500, detail="Supabase no está configurado.")', r)
        self.assertIn('dias_int = max(1, min(int(dias), 365))', r)
        self.assertIn('except Exception:\n        dias_int = 30', r)
        self.assertIn('(datetime.utcnow() - timedelta(days=dias_int)).isoformat() + "Z"', r)

    def test_reads_keep_fail_soft_and_limits(self):
        r = self.router
        self.assertIn('usage_rows = await get_rows(', r)
        self.assertIn('"usage_logs"', r)
        self.assertIn('"limit": "20000"', r)
        self.assertIn('session_rows = await get_rows(', r)
        self.assertIn('"module_sessions"', r)
        self.assertIn('"limit": "50000"', r)
        self.assertGreaterEqual(r.count('except Exception:'), 3)
        self.assertIn('usage_rows = []', r)
        self.assertIn('session_rows = []', r)

    def test_aggregation_and_sort_contracts_are_preserved(self):
        r = self.router
        self.assertIn('slot["segundos"] += int(row.get("segundos") or 0)', r)
        self.assertIn('slot["costo_usd"] += float(row.get("costo_usd") or 0)', r)
        self.assertIn('slot["tokens_in"] += int(row.get("tokens_in") or 0)', r)
        self.assertIn('slot["tokens_out"] += int(row.get("tokens_out") or 0)', r)
        self.assertIn('slot["unidades"] += int(row.get("unidades") or 0)', r)
        self.assertIn('modulos_arr.sort(key=lambda x: (x["segundos"], x["costo_usd"]), reverse=True)', r)
        self.assertIn('herramientas_arr.sort(key=lambda x: (x["costo_usd"], x["llamadas"]), reverse=True)', r)
        self.assertIn('"por_modulo": modulos_arr', r)
        self.assertIn('"por_herramienta": herramientas_arr', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/admin_usage.py", "exec")
        compile(self.core, "core/legacy_admin.py", "exec")


if __name__ == "__main__":
    unittest.main()
