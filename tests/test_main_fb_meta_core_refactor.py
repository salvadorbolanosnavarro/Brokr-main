"""Permanent guards for _get_fb_meta's Core database contract."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
STORE = ROOT / "core" / "facebook_connection_store.py"


class MainFacebookMetaCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.store = STORE.read_text(encoding="utf-8")
        start = cls.store.index("async def get_facebook_meta(user_id: str) -> dict:")
        end = cls.store.index("async def patch_facebook_meta(", start)
        cls.block = cls.store[start:end]

    def test_main_and_store_compile(self):
        compile(self.source, "main.py", "exec")
        compile(self.store, "core/facebook_connection_store.py", "exec")
        self.assertIn("from core.facebook_connection_store import get_facebook_meta as _get_fb_meta", self.source)
        self.assertNotIn("async def _get_fb_meta(", self.source)

    def test_fb_meta_preserves_http_and_transport_error_contract(self):
        block = self.block
        self.assertIn('rows = await get_rows(\n            "user_integrations",', block)
        self.assertIn('"provider": "eq.facebook"', block)
        self.assertIn('"select": "meta"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=10", block)
        self.assertIn("except httpx.HTTPStatusError:", block)
        self.assertIn('raise HTTPException(status_code=400, detail="Facebook no conectado")', block)
        self.assertIn("if not rows:", block)
        self.assertIn('meta_raw = rows[0].get("meta", "{}")', block)
        before_meta_parse = block.split('meta_raw = rows[0].get("meta", "{}")', 1)[0]
        self.assertNotIn("except Exception:", before_meta_parse)
        self.assertNotIn("/rest/v1/user_integrations", block)
        self.assertNotIn('"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"', block)


if __name__ == "__main__":
    unittest.main()
