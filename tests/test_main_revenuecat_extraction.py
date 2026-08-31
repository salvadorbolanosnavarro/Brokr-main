from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "revenuecat.py"


class MainRevenueCatExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_prepared_router_has_revenuecat_route(self):
        self.assertIn('@router.post("/subscription/revenuecat-webhook")', self.router)

    def test_auth_contract_is_preserved(self):
        r = self.router
        self.assertIn('legacy_main_settings.revenuecat_webhook_auth', r)
        self.assertIn('raise HTTPException(status_code=503, detail="Webhook no disponible.")', r)
        self.assertIn('hmac.compare_digest', r)
        self.assertIn('raise HTTPException(status_code=403, detail="No autorizado.")', r)

    def test_event_mapping_and_fail_soft_write_are_preserved(self):
        r = self.router
        for event in ('INITIAL_PURCHASE', 'RENEWAL', 'UNCANCELLATION', 'NON_RENEWING_PURCHASE', 'SUBSCRIPTION_EXTENDED'):
            self.assertIn(event, r)
        self.assertIn('event_type == "EXPIRATION"', r)
        self.assertIn('event_type == "BILLING_ISSUE"', r)
        self.assertIn('event_type == "CANCELLATION"', r)
        self.assertIn('await post_rows(', r)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', r)
        self.assertIn('except httpx.HTTPStatusError:\n        pass', r)
        self.assertNotIn('/rest/v1/', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/revenuecat.py", "exec")


if __name__ == "__main__":
    unittest.main()
