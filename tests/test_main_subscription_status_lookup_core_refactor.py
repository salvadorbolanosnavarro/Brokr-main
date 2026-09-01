"""Permanent guards for subscription_status' suscripciones read through Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "subscription_status.py"


class MainSubscriptionStatusLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = ROUTER.read_text(encoding="utf-8")

    def test_status_lookup_uses_shared_org_or_user_lookup(self):
        block = self.block
        self.assertIn("from core.subscriptions import (", block)
        self.assertIn("find_latest_subscription", block)
        self.assertIn(
            "row = await find_latest_subscription(user_id, org_id, timeout=8)",
            block,
        )
        self.assertIn("if not row:", block)
        self.assertIn('"status": "sin_suscripcion"', block)

    def test_status_lookup_logs_http_failures_instead_of_silencing_them(self):
        block = self.block
        lookup_start = block.index("    org_id = await get_org_id_for_user(user_id)")
        lookup_end = block.index("    estado = row.get(\"status\")", lookup_start)
        lookup = block[lookup_start:lookup_end]
        self.assertIn("except httpx.HTTPStatusError as exc:", lookup)
        self.assertIn("log.error(", lookup)
        self.assertNotIn("except Exception:", lookup)
        self.assertNotIn("/rest/v1/suscripciones", lookup)
        self.assertIn("asyncio.create_task(expire_trial_subscription", block)

    def test_does_not_build_an_org_id_only_filter_directly(self):
        # The router must delegate the org_id/user_id fallback to
        # find_latest_subscription instead of re-inlining an org_id-only
        # PostgREST filter that breaks when org_id is None.
        self.assertNotIn('{"org_id": f"eq.{org_id}", "select": "*"', self.block)


if __name__ == "__main__":
    unittest.main()
