"""Permanent guards for Stripe webhook subscription writes routed through core.database."""
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
        end = source.index(
            '\n\n# ════════════════════════════════════════════════════════════════\n# Contactos / Importar desde EasyBroker',
            start,
        )
        cls.block = source[start:end]

    def _checkout_block(self):
        checkout = self.block.split('if event_type == "checkout.session.completed":', 1)[1]
        return checkout.split('elif event_type in ("customer.subscription.updated"', 1)[0]

    def _migrated_post_block(self):
        checkout = self._checkout_block()
        start = checkout.index('            try:\n                await post_rows(')
        end = checkout.index('\n\n', start)
        return checkout[start:end]

    def test_checkout_subscription_post_routes_through_core(self):
        post = self._migrated_post_block()
        self.assertIn('await post_rows(', post)
        self.assertIn('"suscripciones"', post)
        self.assertIn('sb,', post)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', post)
        self.assertIn('timeout=10', post)
        self.assertIn('except httpx.HTTPStatusError:', post)

    def test_checkout_post_keeps_http_fail_soft_and_transport_fail_loud(self):
        post = self._migrated_post_block()
        self.assertIn('except httpx.HTTPStatusError:', post)
        self.assertIn('pass', post)
        self.assertNotIn('/rest/v1/suscripciones', post)
        self.assertNotIn('except Exception:', post)

    def test_status_updates_route_through_core_and_keep_http_fail_soft(self):
        updated = self.block.split('elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):', 1)[1]
        self.assertGreaterEqual(updated.count('await patch_rows('), 2)
        self.assertIn('{"stripe_subscription_id": f"eq.{subscription_id}"}', updated)
        self.assertIn('{"status": new_status, "updated_at": datetime.utcnow().isoformat()}', updated)
        self.assertIn('{"status": "past_due", "updated_at": datetime.utcnow().isoformat()}', updated)
        self.assertGreaterEqual(updated.count('except httpx.HTTPStatusError:'), 2)
        self.assertNotIn('/rest/v1/suscripciones?stripe_subscription_id=eq.', updated)


if __name__ == "__main__":
    unittest.main()
