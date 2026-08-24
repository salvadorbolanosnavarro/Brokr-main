"""Permanent guards for extracting POST /facebook/select-ad-account from main.py."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_select_ad_account.py"


class MainFacebookSelectAdAccountExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_leaves_main_and_router_is_mounted(self):
        self.assertNotIn('@app.post("/facebook/select-ad-account")', self.main)
        self.assertNotIn("class FbSelectAdAccountRequest", self.main)
        self.assertIn(
            "from routers.facebook_select_ad_account import router as facebook_select_ad_account_router",
            self.main,
        )
        self.assertIn("app.include_router(facebook_select_ad_account_router)", self.main)
        self.assertIn('@router.post("/facebook/select-ad-account")', self.router)
        self.assertIn("class FbSelectAdAccountRequest(BaseModel):", self.router)

    def test_authorization_write_and_response_stay_intact(self):
        source = self.router
        self.assertIn("user_id = await exigir_gestion_integraciones(request)", source)
        self.assertIn("await patch_facebook_meta(", source)
        self.assertIn('"ad_account_id": req.account_id', source)
        self.assertIn('"ad_account_name": req.account_name or req.account_id', source)
        self.assertIn('return {"ok": True, "account_id": req.account_id}', source)

    def test_router_has_no_main_or_direct_storage_dependency_and_compiles(self):
        self.assertNotIn("from main import", self.router)
        self.assertNotIn("post_rows(", self.router)
        self.assertNotIn("get_rows(", self.router)
        self.assertIn(
            "from core.facebook_connection_store import patch_facebook_meta",
            self.router,
        )
        self.assertIn(
            "from routers.organizaciones import exigir_gestion_integraciones",
            self.router,
        )
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_select_ad_account.py", "exec")


if __name__ == "__main__":
    unittest.main()
