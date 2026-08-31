"""Permanent guards for Facebook OAuth callback extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_oauth_callback.py"


class FacebookOauthCallbackExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_main_delegates_callback_to_router(self):
        self.assertNotIn('@app.get("/facebook/callback")', self.main)
        self.assertIn(
            "from routers.facebook_oauth_callback import router as facebook_oauth_callback_router",
            self.main,
        )
        self.assertIn("app.include_router(facebook_oauth_callback_router)", self.main)

    def test_router_preserves_exchange_and_fail_closed_behavior(self):
        router = self.router
        self.assertIn('@router.get("/facebook/callback")', router)
        self.assertIn('code: str = Query(...)', router)
        self.assertIn('state: str = Query(None)', router)
        self.assertIn('redirect_uri: str = Query(None)', router)
        self.assertIn('settings.legacy_main_fb_app_id', router)
        self.assertIn('settings.legacy_main_fb_app_secret', router)
        self.assertIn('settings.legacy_main_frontend_url', router)
        self.assertIn('"FB_APP_ID o FB_APP_SECRET no configurados en el servidor."', router)
        self.assertIn('"No se pudo completar la conexión con Facebook"', router)
        self.assertIn('status_code=400', router)
        self.assertIn('"grant_type": "fb_exchange_token"', router)
        self.assertIn('"fb_exchange_token": short_token', router)
        self.assertIn('long_response is None or long_response.status_code != 200', router)
        self.assertIn('"Facebook no entregó un token de larga duración, así que no se guardó "', router)
        self.assertIn('except (TypeError, ValueError):', router)
        self.assertIn('FB_TOKEN_DEFAULT_LIFETIME_SECONDS', router)
        self.assertIn('debug_facebook_token(client, long_token)', router)
        self.assertIn('FACEBOOK_REQUIRED_SCOPES', router)
        self.assertIn('"me/accounts"', router)
        self.assertIn('"fields": "id,name,access_token"', router)
        self.assertIn('"limit": "100"', router)
        self.assertIn('"No se encontraron páginas administradas en esta cuenta de Facebook. "', router)
        self.assertIn('"page_token": page.get("access_token", "")', router)
        self.assertIn('"user_token": long_token', router)
        self.assertIn('"token_expires_in": expires_in', router)
        self.assertIn('"scopes_faltantes": missing_scopes', router)
        self.assertNotIn("from main import", router)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_oauth_callback.py", "exec")


if __name__ == "__main__":
    unittest.main()
