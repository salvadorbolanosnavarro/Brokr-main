"""Permanent guards for POST /facebook/refresh-token living outside main.py."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_refresh_token.py"


class FacebookRefreshTokenExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_removed_from_main_and_router_mounted(self):
        self.assertNotIn('@app.post("/facebook/refresh-token")', self.main)
        self.assertNotIn("async def facebook_refresh_token(", self.main)
        self.assertIn(
            "from routers.facebook_refresh_token import router as facebook_refresh_token_router",
            self.main,
        )
        self.assertIn("app.include_router(facebook_refresh_token_router)", self.main)
        self.assertIn('@router.post("/facebook/refresh-token")', self.router)

    def test_router_preserves_authorization_and_configuration_failures(self):
        self.assertIn("user_id = await exigir_gestion_integraciones(request)", self.router)
        self.assertIn("if not fb_app_id or not fb_app_secret:", self.router)
        self.assertIn('status_code=500, detail="FB_APP_ID o FB_APP_SECRET no configurados."', self.router)
        self.assertIn("row = await get_facebook_meta_row(user_id)", self.router)
        self.assertIn('status_code=400, detail="No hay conexión de Facebook que renovar."', self.router)

    def test_router_preserves_exchange_and_error_contract(self):
        self.assertIn('"grant_type": "fb_exchange_token"', self.router)
        self.assertIn('"fb_exchange_token": user_token', self.router)
        self.assertIn('"oauth/access_token"', self.router)
        self.assertIn("if response is None or response.status_code != 200:", self.router)
        self.assertIn("status_code=502", self.router)
        self.assertIn("_fb_friendly_error(", self.router)
        self.assertIn("No se pudo renovar la conexión con Facebook. Reconéctala desde tu perfil", self.router)
        self.assertIn("Facebook no devolvió un token nuevo. Reconecta desde tu perfil.", self.router)

    def test_router_preserves_lifetime_debug_and_persistence(self):
        self.assertIn("expires_in = int(data.get(\"expires_in\") or 0)", self.router)
        self.assertIn("except (TypeError, ValueError):", self.router)
        self.assertIn("info = await debug_facebook_token(client, new_token)", self.router)
        self.assertIn("lifetime = expires_in or FB_TOKEN_DEFAULT_LIFETIME_SECONDS", self.router)
        self.assertIn('"user_token": new_token', self.router)
        self.assertIn('"token_expires_at": expires_at', self.router)
        self.assertIn('"scopes": info.get("scopes") or meta.get("scopes") or []', self.router)
        self.assertIn('"token_refreshed_at": datetime.now(timezone.utc).isoformat()', self.router)
        self.assertIn("await patch_facebook_meta(", self.router)
        self.assertIn('"dias_restantes": int(lifetime / 86400)', self.router)

    def test_router_has_no_main_dependency_and_files_compile(self):
        self.assertNotIn("from main import", self.router)
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_refresh_token.py", "exec")


if __name__ == "__main__":
    unittest.main()
