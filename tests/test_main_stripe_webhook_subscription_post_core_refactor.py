"""Permanent guards for Stripe webhook subscription writes routed through core.database."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "stripe_webhook.py"


class MainStripeWebhookSubscriptionPostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.block = ROUTER.read_text(encoding="utf-8")

    def _checkout_block(self):
        checkout = self.block.split('if event_type == "checkout.session.completed":', 1)[1]
        return checkout.split('elif event_type in ("customer.subscription.updated"', 1)[0]

    def test_checkout_subscription_post_routes_through_core(self):
        checkout = self._checkout_block()
        self.assertIn('await post_rows(', checkout)
        self.assertIn('"suscripciones"', checkout)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', checkout)
        self.assertIn('timeout=10', checkout)
        self.assertIn('except httpx.HTTPStatusError:', checkout)
        self.assertNotIn('/rest/v1/suscripciones', checkout)

    def test_status_updates_route_through_core_and_keep_http_fail_soft(self):
        updated = self.block.split('elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):', 1)[1]
        self.assertGreaterEqual(updated.count('await patch_rows('), 2)
        self.assertIn('{"stripe_subscription_id": f"eq.{subscription_id}"}', updated)
        self.assertIn('{"status": new_status, "updated_at": datetime.utcnow().isoformat()}', updated)
        self.assertIn('{"status": "past_due", "updated_at": datetime.utcnow().isoformat()}', updated)
        self.assertGreaterEqual(updated.count('except httpx.HTTPStatusError:'), 2)
        self.assertNotIn('/rest/v1/', updated)

    def test_main_no_longer_owns_webhook(self):
        self.assertNotIn('@app.post("/subscription/webhook")', self.main)
        self.assertIn('app.include_router(stripe_webhook_router)', self.main)
        compile(self.block, "routers/stripe_webhook.py", "exec")


if __name__ == "__main__":
    unittest.main()
