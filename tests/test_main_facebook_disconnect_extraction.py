"""Permanent guards for static extraction of DELETE /facebook/connection."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_disconnect.py"


class FacebookDisconnectExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_removed_from_main_and_router_mounted(self):
        self.assertNotIn('@app.delete("/facebook/connection")', self.main)
        self.assertNotIn("async def facebook_disconnect(", self.main)
        self.assertIn("from routers.facebook_disconnect import router as facebook_disconnect_router", self.main)
        self.assertIn("app.include_router(facebook_disconnect_router)", self.main)

    def test_router_preserves_authorization_and_exact_delete_scope(self):
        self.assertIn('@router.delete("/facebook/connection")', self.router)
        self.assertIn("user_id = await exigir_gestion_integraciones(request)", self.router)
        self.assertIn('if not settings.supabase_url or not settings.supabase_service_key:', self.router)
        self.assertIn('status_code=500, detail="Supabase no configurado"', self.router)
        self.assertIn('"user_integrations"', self.router)
        self.assertIn('{"user_id": f"eq.{user_id}", "provider": "eq.facebook"}', self.router)
        self.assertIn("timeout=10", self.router)
        self.assertIn("except httpx.HTTPStatusError:", self.router)
        self.assertIn('return {"ok": True}', self.router)

    def test_router_does_not_import_main_or_broaden_failure_handling(self):
        self.assertNotIn("from main import", self.router)
        self.assertNotIn("except Exception", self.router)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_disconnect.py", "exec")


if __name__ == "__main__":
    unittest.main()
