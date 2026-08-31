"""Permanent guards for subscription_status' suscripciones read through Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "subscription_status.py"


class MainSubscriptionStatusLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = ROUTER.read_text(encoding="utf-8")

    def test_status_lookup_uses_core_and_preserves_http_empty_fallback(self):
        block = self.block
        self.assertIn('subscription_rows = await get_rows(\n            "suscripciones",', block)
        self.assertIn('"org_id": f"eq.{org_id}"', block)
        self.assertIn('"select": "*"', block)
        self.assertIn('"order": "updated_at.desc"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=8", block)
        self.assertIn("except httpx.HTTPStatusError:\n        subscription_rows = []", block)
        self.assertIn("if not subscription_rows:", block)
        self.assertIn('"status": "sin_suscripcion"', block)
        self.assertIn("row = subscription_rows[0]", block)

    def test_status_lookup_does_not_broaden_scope_and_keeps_trial_expiration(self):
        block = self.block
        lookup_start = block.index("    org_id = await get_org_id_for_user(user_id)")
        lookup_end = block.index("    row = subscription_rows[0]", lookup_start)
        lookup = block[lookup_start:lookup_end]
        self.assertNotIn("except Exception:", lookup)
        self.assertNotIn("/rest/v1/suscripciones", lookup)
        self.assertIn("asyncio.create_task(expire_trial_subscription", block)


if __name__ == "__main__":
    unittest.main()
