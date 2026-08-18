"""Permanent guards for subscription_cancel's initial suscripciones read through Core."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainSubscriptionCancelLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.post("/subscription/cancel")')
        end = cls.source.index('@app.post("/subscription/revenuecat-webhook")', start)
        cls.block = cls.source[start:end]

    def test_cancel_lookup_uses_core_and_preserves_http_empty_404(self):
        block = self.block
        self.assertIn('subscription_rows = await get_rows(\n            "suscripciones",', block)
        self.assertIn('"user_id": f"eq.{user_id}"', block)
        self.assertIn('"select": "stripe_subscription_id,status"', block)
        self.assertIn('"order": "updated_at.desc"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=8", block)
        self.assertIn("except httpx.HTTPStatusError:\n        subscription_rows = []", block)
        self.assertIn("row = subscription_rows[0] if subscription_rows else {}", block)
        self.assertIn('raise HTTPException(status_code=404, detail="No se encontró suscripción activa.")', block)

    def test_cancel_lookup_does_not_broaden_scope_and_downstream_patch_is_core_routed(self):
        block = self.block
        lookup_end = block.index("    subscription_id = row.get", block.index("subscription_rows = await get_rows"))
        lookup = block[:lookup_end]
        self.assertNotIn("except Exception:", lookup)
        self.assertNotIn("/rest/v1/suscripciones", lookup)
        self.assertIn('https://api.stripe.com/v1/subscriptions/{subscription_id}', block)
        self.assertIn('await patch_rows(', block)
        self.assertIn('{"user_id": f"eq.{user_id}"}', block)
        self.assertNotIn('/rest/v1/suscripciones?user_id=eq.{user_id}', block)


if __name__ == "__main__":
    unittest.main()
