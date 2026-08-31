"""Permanent guard: service-role policies delegate directly to Core without legacy adapters."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ENTERPRISE = ROOT / "routers" / "subscription_enterprise.py"
STRIPE_WEBHOOK = ROOT / "routers" / "stripe_webhook.py"
STRIPE_CORE = ROOT / "core" / "stripe.py"


class MainNoLegacyServiceAdaptersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.enterprise = ENTERPRISE.read_text(encoding="utf-8")
        cls.stripe_webhook = STRIPE_WEBHOOK.read_text(encoding="utf-8")
        cls.stripe_core = STRIPE_CORE.read_text(encoding="utf-8")
        cls.extracted = cls.enterprise + "\n" + cls.stripe_webhook + "\n" + cls.stripe_core

    def test_local_service_adapters_are_gone(self):
        for source in (self.source, self.enterprise, self.stripe_webhook, self.stripe_core):
            self.assertNotIn('async def _sb_service_get(', source)
            self.assertNotIn('async def _sb_service_patch(', source)
            self.assertNotIn('_sb_service_get(', source)
            self.assertNotIn('_sb_service_patch(', source)

    def test_named_core_policies_are_used(self):
        combined = self.source + "\n" + self.extracted
        self.assertIn('get_service_json_or_empty', combined)
        self.assertIn('patch_rows_ignoring_http_status', combined)
        self.assertGreaterEqual(combined.count('get_service_json_or_empty('), 6)
        self.assertGreaterEqual(combined.count('patch_rows_ignoring_http_status('), 4)

    def test_postgrest_implementation_remains_absent(self):
        for source in (self.source, self.enterprise, self.stripe_webhook, self.stripe_core):
            self.assertNotIn('/rest/v1/', source)


if __name__ == '__main__':
    unittest.main()
