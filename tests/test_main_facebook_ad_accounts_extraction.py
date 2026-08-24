"""Permanent guards for GET /facebook/ad-accounts extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_ad_accounts.py"


class FacebookAdAccountsExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_removed_from_main_and_router_mounted(self):
        self.assertNotIn('@app.get("/facebook/ad-accounts")', self.main)
        self.assertNotIn("async def facebook_ad_accounts(", self.main)
        self.assertIn("from routers.facebook_ad_accounts import router as facebook_ad_accounts_router", self.main)
        self.assertIn("app.include_router(facebook_ad_accounts_router)", self.main)

    def test_router_preserves_auth_token_and_active_account_contract(self):
        r = self.router
        self.assertIn('@router.get("/facebook/ad-accounts")', r)
        self.assertIn("user_id = await get_user_id_from_token(request)", r)
        self.assertIn('status_code=401, detail="No autenticado"', r)
        self.assertIn("meta = await get_facebook_meta(user_id)", r)
        self.assertIn('detail="Token de usuario sin permisos de ads. Reconecta tu Facebook."', r)
        self.assertIn('"me/adaccounts"', r)
        self.assertIn('"fields": "id,name,account_status,currency"', r)
        self.assertIn('a.get("account_status", 0) == 1', r)

    def test_router_preserves_promote_pages_batch_and_safe_projection(self):
        r = self.router
        self.assertIn("resultados = await _fb_batch(", r)
        self.assertIn("/promote_pages?fields=id&limit=100", r)
        self.assertIn('if res.get("code") == 200 and isinstance(cuerpo, dict):', r)
        self.assertIn('"currency": a.get("currency", "MXN")', r)
        self.assertIn('"promote_pages": page_ids', r)
        self.assertIn('return {"accounts": active}', r)
        self.assertNotIn('"user_token":', r)
        self.assertNotIn('"access_token":', r)
        self.assertNotIn("from main import", r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_ad_accounts.py", "exec")


if __name__ == "__main__":
    unittest.main()
