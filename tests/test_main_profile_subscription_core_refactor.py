"""Keep /profile/status's subscription read behind core.database."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "profile_status.py"


class MainProfileSubscriptionCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = ROUTER.read_text(encoding="utf-8")

    def test_profile_subscription_uses_core(self):
        block = self.block
        self.assertIn('sub_rows = await get_rows(\n                "suscripciones",', block)
        self.assertIn('"org_id": f"eq.{org_id}"', block)
        self.assertIn('"select": "*"', block)
        self.assertIn('"order": "updated_at.desc"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=6", block)
        self.assertIn("if sub_rows:\n                row = sub_rows[0]", block)
        self.assertNotIn("/rest/v1/suscripciones", block)

    def test_profile_subscription_keeps_fail_soft_trial_contract(self):
        block = self.block
        self.assertIn('sub_state = {"active": False, "plan": None, "status": "sin_suscripcion"}', block)
        self.assertIn('status = row.get("status")', block)
        self.assertIn('active = status in ("active", "trialing")', block)
        self.assertIn('trial_has_expired(row.get("trial_hasta"))', block)
        self.assertIn('asyncio.create_task(expire_trial_subscription(row.get("id")))', block)
        self.assertIn('"plan": row.get("plan_nombre")', block)
        self.assertIn("except Exception:\n        pass", block)


if __name__ == "__main__":
    unittest.main()
