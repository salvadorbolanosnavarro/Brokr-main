"""Permanent guards for Facebook save-page extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_save_page.py"


class FacebookSavePageExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_main_delegates_model_and_route(self):
        self.assertNotIn("class FbSavePageRequest(BaseModel):", self.main)
        self.assertNotIn('@app.post("/facebook/save-page")', self.main)
        self.assertIn(
            "from routers.facebook_save_page import router as facebook_save_page_router",
            self.main,
        )
        self.assertIn("app.include_router(facebook_save_page_router)", self.main)

    def test_router_preserves_authorization_and_token_lifecycle(self):
        router = self.router
        self.assertIn("class FbSavePageRequest(BaseModel):", router)
        self.assertIn("user_token: str = \"\"", router)
        self.assertIn("token_expires_at: str = \"\"", router)
        self.assertIn('@router.post("/facebook/save-page")', router)
        self.assertIn("user_id = await exigir_gestion_integraciones(request)", router)
        self.assertIn('raise HTTPException(status_code=401, detail="No autenticado")', router)
        self.assertIn("settings.supabase_url", router)
        self.assertIn("settings.supabase_anon_key", router)
        self.assertIn('raise HTTPException(status_code=500, detail="Supabase no configurado")', router)
        self.assertIn("debug_facebook_token(token_client, req.user_token)", router)
        self.assertIn('info.get("expires_at")', router)
        self.assertIn('info.get("data_access_expires_at")', router)
        self.assertIn("FB_TOKEN_DEFAULT_LIFETIME_SECONDS", router)

    def test_router_preserves_account_selection_and_fail_soft_graph_reads(self):
        router = self.router
        self.assertIn('params={"fields": "picture.type(square)"}', router)
        self.assertIn('"me/adaccounts"', router)
        self.assertIn('"fields": "id,name,account_status,currency"', router)
        self.assertIn('"limit": "50"', router)
        self.assertIn('account.get("account_status") == 1', router)
        self.assertIn('f"{account[\'id\']}/promote_pages"', router)
        self.assertIn('params={"fields": "id", "limit": "100"}', router)
        self.assertIn('if not chosen and accounts:', router)
        self.assertIn('chosen = accounts[0]', router)

    def test_router_preserves_encryption_org_and_supabase_semantics(self):
        router = self.router
        self.assertIn('"user_token": encrypt_facebook_secret(req.user_token)', router)
        self.assertIn('"org_id": await get_org_id_for_user(user_id)', router)
        self.assertIn('"api_key": encrypt_facebook_secret(req.page_token)', router)
        self.assertIn('"meta": json.dumps(meta)', router)
        self.assertIn('"updated_at": datetime.utcnow().isoformat()', router)
        self.assertIn('"user_integrations"', router)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', router)
        self.assertIn('except httpx.HTTPStatusError:', router)
        self.assertIn('"scopes_faltantes": [scope for scope in FACEBOOK_REQUIRED_SCOPES if scope not in scopes]', router)
        self.assertNotIn("from main import", router)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_save_page.py", "exec")


if __name__ == "__main__":
    unittest.main()
