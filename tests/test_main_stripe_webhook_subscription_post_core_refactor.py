"""Permanent guard for Stripe webhook subscription POST routed through core.database."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainStripeWebhookSubscriptionPostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = MAIN.read_text(encoding="utf-8")
        start = source.index('@app.post("/subscription/webhook")')
        end = source.index('\n\n@app.post("/subscription/activate")', start)
        cls.block = source[start:end]

    def test_checkout_subscription_post_routes_through_core(self):
        block = self.block
        checkout = block[block.index('if event_type == "checkout.session.completed":'):]
        self.assertIn('await post_rows(', checkout)
        self.assertIn('"suscripciones"', checkout)
        self.assertIn('sb,', checkout)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', checkout)
        self.assertIn('timeout=10', checkout)
        self.assertIn('except httpx.HTTPStatusError:', checkout)
        self.assertNotIn('except Exception:', checkout.split('elif event_type in ("customer.subscription.updated"', 1)[0])

    def test_checkout_post_keeps_http_fail_soft_and_transport_fail_loud(self):
        block = self.block
        checkout = block.split('if event_type == "checkout.session.completed":', 1)[1]
        checkout = checkout.split('elif event_type in ("customer.subscription.updated"', 1)[0]
        self.assertIn('except httpx.HTTPStatusError:', checkout)
        self.assertIn('pass', checkout)
        self.assertNotIn('/rest/v1/suscripciones', checkout)
        self.assertNotIn('except Exception:', checkout)

    def test_other_webhook_subscription_writes_are_untouched(self):
        block = self.block
        updated = block.split('elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):', 1)[1]
        self.assertIn('await client.patch(', updated)
        self.assertIn('/rest/v1/suscripciones?stripe_subscription_id=eq.', updated)


if __name__ == "__main__":
    unittest.main()
