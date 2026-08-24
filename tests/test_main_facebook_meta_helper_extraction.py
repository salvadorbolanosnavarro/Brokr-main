"""Permanent guards for the strict Facebook metadata helper living in Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
STORE = ROOT / "core" / "facebook_connection_store.py"


class FacebookMetaHelperExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.store = STORE.read_text(encoding="utf-8")

    def test_main_delegates_strict_meta_reader_to_core(self):
        self.assertNotIn("async def _get_fb_meta(", self.main)
        self.assertIn("from core.facebook_connection_store import get_facebook_meta as _get_fb_meta", self.main)
        self.assertIn("await _get_fb_meta(", self.main)

    def test_core_preserves_legacy_error_and_decryption_semantics(self):
        store = self.store
        self.assertIn("async def get_facebook_meta(user_id: str) -> dict:", store)
        self.assertIn('"select": "meta"', store)
        self.assertIn('except httpx.HTTPStatusError:\n        raise HTTPException(status_code=400, detail="Facebook no conectado")', store)
        self.assertIn('if not rows:\n        raise HTTPException(status_code=400, detail="Facebook no conectado")', store)
        self.assertIn('except Exception:\n        return {}', store)
        self.assertIn('meta["user_token"] = decrypt_facebook_secret(meta["user_token"])', store)
        self.assertIn("return meta", store)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.store, "core/facebook_connection_store.py", "exec")


if __name__ == "__main__":
    unittest.main()
