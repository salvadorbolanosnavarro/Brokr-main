"""Permanent guards for Facebook connection metadata writes living in Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
STORE = ROOT / "core" / "facebook_connection_store.py"


class FacebookConnectionWriteExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.store = STORE.read_text(encoding="utf-8")

    def test_main_delegates_metadata_writes_to_core(self):
        self.assertIn(
            "from core.facebook_connection_store import patch_facebook_meta as _fb_patch_meta",
            self.main,
        )
        self.assertNotIn("async def _fb_patch_meta(", self.main)
        self.assertIn("await _fb_patch_meta(", self.main)

    def test_store_preserves_encryption_org_and_upsert_contract(self):
        store = self.store
        self.assertIn("async def patch_facebook_meta(", store)
        self.assertIn("cur = await get_facebook_meta_row(user_id)", store)
        self.assertIn('meta["user_token"] = encrypt_facebook_secret(meta["user_token"])', store)
        self.assertIn('"org_id": await get_org_id_for_user(user_id)', store)
        self.assertIn('"api_key": encrypt_facebook_secret(page_token)', store)
        self.assertIn('"meta": json.dumps(meta)', store)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', store)
        self.assertIn("except httpx.HTTPStatusError:\n        pass", store)
        self.assertNotIn("except Exception:\n        pass", store)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.store, "core/facebook_connection_store.py", "exec")


if __name__ == "__main__":
    unittest.main()
