from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "stripe_webhook.py"


class StripeWebhookExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_lives_only_in_router(self):
        self.assertIn('@router.post("/subscription/webhook")', self.router)
        self.assertNotIn('@app.post("/subscription/webhook")', self.main)
        self.assertIn('app.include_router(stripe_webhook_router)', self.main)

    def test_signature_contract_is_hardened(self):
        r = self.router
        self.assertIn('if not STRIPE_WEBHOOK_SECRET:', r)
        self.assertIn('raise HTTPException(status_code=503, detail="Webhook no disponible.")', r)
        self.assertIn('STRIPE_SIGNATURE_TOLERANCE_SECONDS = 300', r)
        self.assertIn('signed_payload = f"{ts}.{payload.decode()}"', r)
        self.assertIn('hmac.compare_digest(expected, candidate)', r)
        self.assertIn('if abs(current - timestamp) > max(0, int(tolerance)):', r)
        self.assertIn('detail="Firma de webhook expirada."', r)
        self.assertIn('elif key == "v1" and value:', r)

    def test_checkout_completed_contract_is_preserved(self):
        r = self.router
        self.assertIn('event_type == "checkout.session.completed"', r)
        self.assertIn('"status": "trialing" if es_trial else "active"', r)
        self.assertIn('await patch_rows_ignoring_http_status(', r)
        self.assertIn('{"trial_max_usado": True}', r)
        self.assertIn('await activate_enterprise_subscription(', r)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', r)
        self.assertIn('except httpx.HTTPStatusError:\n                pass', r)

    def test_update_delete_and_failed_payment_contracts_are_preserved(self):
        r = self.router
        self.assertIn('event_type in ("customer.subscription.updated", "customer.subscription.deleted")', r)
        self.assertIn('new_status = "canceled"', r)
        self.assertIn('"activo": new_status in ("active", "trialing")', r)
        self.assertIn('event_type == "invoice.payment_failed"', r)
        self.assertIn('"status": "past_due"', r)
        self.assertNotIn('/rest/v1/', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/stripe_webhook.py", "exec")


if __name__ == "__main__":
    unittest.main()
