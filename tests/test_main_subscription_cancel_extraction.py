from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "subscription_cancel.py"


class MainSubscriptionCancelExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_lives_only_in_router(self):
        self.assertIn('@router.post("/subscription/cancel")', self.router)
        self.assertNotIn('@app.post("/subscription/cancel")', self.main)
        self.assertIn('app.include_router(subscription_cancel_router)', self.main)

    def test_cancel_contract_is_preserved(self):
        r = self.router
        self.assertIn('"select": "stripe_subscription_id,status"', r)
        self.assertIn('timeout=8', r)
        self.assertIn('except httpx.HTTPStatusError:\n        subscription_rows = []', r)
        self.assertIn('data={"cancel_at_period_end": "true"}', r)
        self.assertIn('if r_cancel.status_code not in (200, 201):', r)
        self.assertIn('{"status": "canceled", "updated_at": datetime.utcnow().isoformat()}', r)
        self.assertIn('prefer="return=minimal"', r)
        self.assertIn('except httpx.HTTPStatusError:\n        pass', r)
        self.assertNotIn('/rest/v1/', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/subscription_cancel.py", "exec")


if __name__ == "__main__":
    unittest.main()
