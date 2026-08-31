"""Permanent guard for /subscription/activate POST routed through core.database."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "subscription_activate.py"


class MainSubscriptionActivatePostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = ROUTER.read_text(encoding="utf-8")

    def test_activate_post_routes_through_core(self):
        block = self.block
        self.assertIn('await post_rows(', block)
        self.assertIn('"suscripciones"', block)
        self.assertIn('row,', block)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', block)
        self.assertIn('timeout=10', block)
        self.assertNotIn('/rest/v1/suscripciones', block)

    def test_http_fail_soft_transport_fail_loud_is_preserved(self):
        start = self.block.index('    try:\n        await post_rows(')
        post = self.block[start:]
        self.assertIn('except httpx.HTTPStatusError:', post)
        self.assertIn('pass', post)
        self.assertNotIn('except Exception:', post)


if __name__ == "__main__":
    unittest.main()
