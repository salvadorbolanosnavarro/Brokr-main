"""Permanent guards for /profile/status integration reads delegated to Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "profile_status.py"
MAIN = ROOT / "main.py"


class MainProfileStatusCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROUTER.read_text(encoding="utf-8")
        cls.main = MAIN.read_text(encoding="utf-8")

    def test_files_compile(self):
        compile(self.source, "routers/profile_status.py", "exec")
        compile(self.main, "main.py", "exec")

    def test_profile_status_uses_core_and_keeps_fail_soft_contract(self):
        block = self.source
        self.assertIn('rows = await get_rows(\n            "user_integrations",', block)
        self.assertIn('"provider": "in.(easybroker,facebook)"', block)
        self.assertIn('"select": "provider,api_key,meta"', block)
        self.assertIn("timeout=8", block)
        self.assertIn('except Exception:\n        return {"eb": {"configured": False, "masked": ""}, "fb": {"connected": False}}', block)
        self.assertNotIn("/rest/v1/user_integrations", block)
        self.assertNotIn('"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"', block)
        self.assertNotIn('@app.get("/profile/status")', self.main)


if __name__ == "__main__":
    unittest.main()
