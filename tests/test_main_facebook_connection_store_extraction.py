"""Permanent guards for the server-only Facebook integration row reader."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
STORE = ROOT / "core" / "facebook_connection_store.py"
CREATE_AD = ROOT / "routers" / "facebook_create_ad.py"


class FacebookConnectionStoreExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.store = STORE.read_text(encoding="utf-8")
        cls.create_ad = CREATE_AD.read_text(encoding="utf-8")

    def test_main_delegates_connection_row_reads_to_core(self):
        self.assertIn(
            "from core.facebook_connection_store import get_facebook_meta_row as _fb_get_meta_row",
            self.main,
        )
        self.assertNotIn("async def _fb_get_meta_row(", self.main)
        self.assertIn("row = await get_facebook_meta_row(user_id)", self.create_ad)

    def test_store_preserves_server_side_secret_and_fail_soft_contract(self):
        self.assertIn("async def get_facebook_meta_row", self.store)
        self.assertIn('"provider": "eq.facebook"', self.store)
        self.assertIn('"select": "api_key,meta"', self.store)
        self.assertIn("except httpx.HTTPStatusError:\n        return {}", self.store)
        self.assertIn('meta["user_token"] = decrypt_facebook_secret(meta["user_token"])', self.store)
        self.assertIn('"page_token": decrypt_facebook_secret(row.get("api_key", ""))', self.store)
        self.assertNotIn("APIRouter", self.store)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.store, "core/facebook_connection_store.py", "exec")
        compile(self.create_ad, "routers/facebook_create_ad.py", "exec")


if __name__ == "__main__":
    unittest.main()
