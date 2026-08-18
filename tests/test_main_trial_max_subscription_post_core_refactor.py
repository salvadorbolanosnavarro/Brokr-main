"""Permanent guard for trial-max subscription POST routed through core.database."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "subscription_status.py"


class MainTrialMaxSubscriptionPostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = ROUTER.read_text(encoding="utf-8")

    def test_subscription_create_routes_through_core_with_exact_status_contract(self):
        block = self.block
        self.assertIn('await post_rows(', block)
        self.assertIn('"suscripciones"', block)
        self.assertIn('fila,', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=10', block)
        self.assertIn('accepted_statuses=(200, 201)', block)
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertIn('raise HTTPException(status_code=502, detail="No se pudo activar la prueba. Intenta de nuevo.")', block)
        self.assertNotIn('/rest/v1/suscripciones', block)

    def test_trial_burn_patch_routes_through_core_with_legacy_fail_soft_http_status(self):
        block = self.block
        self.assertIn('await patch_rows(', block)
        self.assertIn('"usuarios"', block)
        self.assertIn('{"id": f"eq.{user_id}"}', block)
        self.assertIn('{"trial_max_usado": True}', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=10', block)
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertNotIn('/rest/v1/usuarios', block)
        self.assertLess(block.index('await post_rows('), block.index('await patch_rows('))


if __name__ == "__main__":
    unittest.main()
