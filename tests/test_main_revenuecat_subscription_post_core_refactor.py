"""Permanent guard for RevenueCat subscription POST routed through core.database."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "revenuecat.py"
MAIN = ROOT / "main.py"


class MainRevenueCatSubscriptionPostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = ROUTER.read_text(encoding="utf-8")
        cls.main = MAIN.read_text(encoding="utf-8")

    def test_subscription_write_routes_through_core(self):
        block = self.block
        self.assertIn('await post_rows(', block)
        self.assertIn('"suscripciones"', block)
        self.assertIn('row,', block)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', block)
        self.assertIn('timeout=10', block)
        self.assertNotIn('/rest/v1/suscripciones', block)

    def test_http_fail_soft_transport_fail_loud_contract(self):
        block = self.block
        post = block[block.index('try:\n        await post_rows('):]
        self.assertIn('except httpx.HTTPStatusError:', post)
        self.assertIn('pass', post)
        self.assertNotIn('except Exception:', post)

    def test_main_no_longer_owns_route(self):
        self.assertNotIn('@app.post("/subscription/revenuecat-webhook")', self.main)
        self.assertIn('app.include_router(revenuecat_router)', self.main)


if __name__ == "__main__":
    unittest.main()
