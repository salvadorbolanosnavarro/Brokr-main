"""Permanent guards for non-destructive subscription/user status PATCH migrations."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
STATUS_ROUTER = ROOT / "routers" / "subscription_status.py"
CANCEL_ROUTER = ROOT / "routers" / "subscription_cancel.py"
STRIPE_WEBHOOK = ROOT / "routers" / "stripe_webhook.py"


class MainSubscriptionStatusPatchesCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = STATUS_ROUTER.read_text(encoding="utf-8")
        cls.cancel = CANCEL_ROUTER.read_text(encoding="utf-8")
        cls.stripe_webhook = STRIPE_WEBHOOK.read_text(encoding="utf-8")

    def test_stripe_webhook_status_writes_use_core_and_preserve_http_fail_soft(self):
        block = self.stripe_webhook
        self.assertGreaterEqual(block.count('await patch_rows('), 2)
        self.assertIn('{"stripe_subscription_id": f"eq.{subscription_id}"}', block)
        self.assertIn('{"status": new_status, "updated_at": datetime.utcnow().isoformat()}', block)
        self.assertIn('{"status": "past_due", "updated_at": datetime.utcnow().isoformat()}', block)
        self.assertGreaterEqual(block.count('except httpx.HTTPStatusError:'), 3)
        self.assertNotIn('/rest/v1/', block)

    def test_no_card_trial_grant_was_removed(self):
        # The trial-max endpoint (post_rows for the new subscription, then
        # patch_rows to burn trial_max_usado) was retired along with the
        # no-card trial itself.
        block = self.router
        self.assertNotIn('trial_max_usado', block)
        self.assertNotIn('await post_rows(', block)

    def test_subscription_cancel_local_mark_uses_core_without_changing_stripe_contract(self):
        block = self.cancel
        self.assertIn('https://api.stripe.com/v1/subscriptions/{subscription_id}', block)
        self.assertIn('if r_cancel.status_code not in (200, 201):', block)
        self.assertIn('await patch_rows(', block)
        self.assertIn('{"user_id": f"eq.{user_id}"}', block)
        self.assertIn('{"status": "canceled", "updated_at": datetime.utcnow().isoformat()}', block)
        self.assertIn('timeout=8', block)
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertNotIn('/rest/v1/suscripciones?user_id=eq.{user_id}', block)

    def test_no_broad_exception_hides_transport_failures_in_migrated_blocks(self):
        self.assertNotIn('except Exception:\n        # Historical', self.router)
        self.assertNotIn('except Exception:\n        # Historical', self.cancel)


if __name__ == "__main__":
    unittest.main()
