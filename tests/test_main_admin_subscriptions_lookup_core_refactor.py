"""Permanent guards for admin_list_users' subscriptions read through Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "admin_read.py"


class MainAdminSubscriptionsLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = ROUTER.read_text(encoding="utf-8")

    def test_admin_subscriptions_lookup_uses_core_and_preserves_fail_soft_http_contract(self):
        block = self.block
        self.assertIn('subs = await get_rows(\n            "suscripciones",', block)
        self.assertIn('"select": "user_id,plan_id,plan_nombre,status,updated_at"', block)
        self.assertIn('"order": "updated_at.desc"', block)
        self.assertIn('"limit": "10000"', block)
        self.assertIn("timeout=15", block)
        self.assertIn("except httpx.HTTPStatusError:\n        subs = []", block)
        self.assertIn("for s in subs:", block)

    def test_admin_subscriptions_lookup_does_not_broaden_scope_or_revert_users(self):
        block = self.block
        lookup = block.split("subs_by_user = {}", 1)[0]
        self.assertNotIn("except Exception:", lookup)
        self.assertNotIn("/rest/v1/suscripciones", lookup)
        self.assertIn('users = await get_rows(\n            "usuarios",', block)


if __name__ == "__main__":
    unittest.main()
