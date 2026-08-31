"""Permanent guard for the read-only Facebook connection extraction."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_connection_read.py"
CORE = ROOT / "core" / "facebook_tokens.py"


class FacebookConnectionReadExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")

    def test_connection_read_has_one_home_outside_main(self):
        self.assertNotIn('@app.get("/facebook/connection")', self.main)
        self.assertNotIn("async def facebook_get_connection", self.main)
        self.assertIn('@router.get("/facebook/connection")', self.router)
        self.assertIn("async def facebook_get_connection", self.router)
        self.assertIn(
            "from routers.facebook_connection_read import router as facebook_connection_read_router",
            self.main,
        )
        self.assertIn("app.include_router(facebook_connection_read_router)", self.main)

    def test_browser_response_remains_token_safe_and_fail_soft(self):
        self.assertIn('"tiene_token_ads": bool(meta.get("user_token"))', self.router)
        self.assertNotIn('"page_token":', self.router)
        self.assertNotIn('"user_token":', self.router)
        self.assertIn("except Exception:\n        pass", self.router)
        self.assertIn('return {"connected": False}', self.router)

    def test_required_scopes_have_one_shared_source(self):
        self.assertIn("FACEBOOK_REQUIRED_SCOPES = (", self.core)
        self.assertIn("from core.facebook_tokens import FACEBOOK_REQUIRED_SCOPES", self.main)
        self.assertNotIn("_FB_SCOPES_REQUERIDOS = [", self.main)
        self.assertIn("FACEBOOK_REQUIRED_SCOPES", self.router)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_connection_read.py", "exec")
        compile(self.core, "core/facebook_tokens.py", "exec")


if __name__ == "__main__":
    unittest.main()
