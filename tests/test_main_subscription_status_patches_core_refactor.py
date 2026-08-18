"""Permanent guards for non-destructive subscription/user status PATCH migrations."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainSubscriptionStatusPatchesCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self, start_marker: str, end_marker: str) -> str:
        start = self.source.index(start_marker)
        end = self.source.index(end_marker, start)
        return self.source[start:end]

    def test_stripe_webhook_status_writes_use_core_and_preserve_http_fail_soft(self):
        block = self._block('@app.post("/subscription/webhook")', '\n\n@app.post("/subscription/activate")')
        self.assertGreaterEqual(block.count('await patch_rows('), 2)
        self.assertIn('{"stripe_subscription_id": f"eq.{subscription_id}"}', block)
        self.assertIn('{"status": new_status, "updated_at": datetime.utcnow().isoformat()}', block)
        self.assertIn('{"status": "past_due", "updated_at": datetime.utcnow().isoformat()}', block)
        self.assertGreaterEqual(block.count('except httpx.HTTPStatusError:'), 2)
        self.assertNotIn('/rest/v1/suscripciones?stripe_subscription_id=eq.', block)

    def test_trial_burn_write_uses_core_after_subscription_create(self):
        block = self._block('@app.post("/subscription/trial-max")', '\n\n@app.post("/subscription/cancel")')
        self.assertIn('await patch_rows(', block)
        self.assertIn('"usuarios",', block)
        self.assertIn('{"id": f"eq.{user_id}"}', block)
        self.assertIn('{"trial_max_usado": True}', block)
        self.assertIn('timeout=10', block)
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertNotIn('/rest/v1/usuarios?id=eq.{user_id}', block)
        self.assertLess(block.index('await post_rows('), block.index('await patch_rows('))

    def test_subscription_cancel_local_mark_uses_core_without_changing_stripe_contract(self):
        block = self._block('@app.post("/subscription/cancel")', '\n\n@app.post("/subscription/revenuecat-webhook")')
        self.assertIn('https://api.stripe.com/v1/subscriptions/{subscription_id}', block)
        self.assertIn('if r_cancel.status_code not in (200, 201):', block)
        self.assertIn('await patch_rows(', block)
        self.assertIn('{"user_id": f"eq.{user_id}"}', block)
        self.assertIn('{"status": "canceled", "updated_at": datetime.utcnow().isoformat()}', block)
        self.assertIn('timeout=8', block)
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertNotIn('/rest/v1/suscripciones?user_id=eq.{user_id}', block)

    def test_no_broad_exception_hides_transport_failures_in_migrated_blocks(self):
        for start, end in [
            ('@app.post("/subscription/trial-max")', '\n\n@app.post("/subscription/cancel")'),
            ('@app.post("/subscription/cancel")', '\n\n@app.post("/subscription/revenuecat-webhook")'),
        ]:
            block = self._block(start, end)
            self.assertNotIn('except Exception:\n        # Historical', block)


if __name__ == "__main__":
    unittest.main()
