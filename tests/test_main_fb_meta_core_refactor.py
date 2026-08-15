"""Permanent guards for _get_fb_meta's Core database contract."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainFacebookMetaCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index("async def _get_fb_meta(user_id: str) -> dict:")
        end = cls.source.index('@app.post("/facebook/ad-description")', start)
        cls.block = cls.source[start:end]

    def test_main_compiles(self):
        compile(self.source, "main.py", "exec")

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
