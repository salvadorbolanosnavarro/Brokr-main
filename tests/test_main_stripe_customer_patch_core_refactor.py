"""Permanent guard for Stripe customer-id persistence routed through core.database."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainStripeCustomerPatchCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = MAIN.read_text(encoding="utf-8")
        start = source.index('async def _get_or_create_stripe_customer(')
        end = source.index('\n\n@app.post("/subscription/checkout")', start)
        cls.block = source[start:end]

    def test_customer_id_patch_routes_through_core(self):
        block = self.block
        self.assertIn('await patch_rows(', block)
        self.assertIn('"usuarios"', block)
        self.assertIn('{"id": f"eq.{user_id}"}', block)
        self.assertIn('{"stripe_customer_id": customer_id}', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=10', block)
        self.assertNotIn('/rest/v1/usuarios', block)

    def test_http_fail_soft_transport_fail_loud_contract(self):
        block = self.block
        patch = block[block.index('try:\n        await patch_rows('):]
        self.assertIn('except httpx.HTTPStatusError:', patch)
        self.assertIn('pass', patch)
        self.assertNotIn('except Exception:', patch)


if __name__ == "__main__":
    unittest.main()
