"""Permanent guards for extracting POST /facebook/select-page from main.py."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_select_page.py"


class MainFacebookSelectPageExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_leaves_main_and_router_is_mounted(self):
        self.assertNotIn('@app.post("/facebook/select-page")', self.main)
        self.assertNotIn("class FbSelectPageRequest", self.main)
        self.assertIn(
            "from routers.facebook_select_page import router as facebook_select_page_router",
            self.main,
        )
        self.assertIn("app.include_router(facebook_select_page_router)", self.main)
        self.assertIn('@router.post("/facebook/select-page")', self.router)
        self.assertIn("class FbSelectPageRequest(BaseModel):", self.router)

    def test_authorization_and_server_side_page_validation_stay_intact(self):
        source = self.router
        self.assertIn("user_id = await exigir_gestion_integraciones(request)", source)
        self.assertIn("row = await get_facebook_meta_row(user_id)", source)
        self.assertIn('detail="Reconecta tu Facebook."', source)
        self.assertIn('"me/accounts"', source)
        self.assertIn('params={"fields": "id,name,access_token", "limit": "100"}', source)
        self.assertIn('p.get("id") == req.page_id', source)
        self.assertIn('detail="No administras esa página o ya no es accesible."', source)
        self.assertIn("new_page_token=page_token", source)
        self.assertIn('{"page_id": req.page_id, "page_name": page_name}', source)
        self.assertIn('return {"ok": True, "page_id": req.page_id, "page_name": page_name}', source)

    def test_router_has_no_main_dependency_and_compiles(self):
        self.assertNotIn("from main import", self.router)
        self.assertIn(
            "from core.facebook_connection_store import get_facebook_meta_row, patch_facebook_meta",
            self.router,
        )
        self.assertIn("from core.facebook_graph import _fb_paginate", self.router)
        self.assertIn(
            "from routers.organizaciones import exigir_gestion_integraciones",
            self.router,
        )
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_select_page.py", "exec")


if __name__ == "__main__":
    unittest.main()
