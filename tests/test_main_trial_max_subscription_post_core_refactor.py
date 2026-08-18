"""Permanent guard for trial-max subscription POST routed through core.database."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainTrialMaxSubscriptionPostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = MAIN.read_text(encoding="utf-8")
        start = source.index('@app.post("/subscription/trial-max")')
        end = source.index('# ════════════════════════════════════════════════════════════════\n# Agendar demo', start)
        cls.block = source[start:end]

    def test_subscription_create_routes_through_core_with_exact_status_contract(self):
        block = self.block
        self.assertIn('await post_rows(', block)
        self.assertIn('"suscripciones"', block)
        self.assertIn('fila,', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=10', block)
        self.assertIn('accepted_statuses=(200, 201)', block)
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertIn(
            'raise HTTPException(status_code=502, detail="No se pudo activar la prueba. Intenta de nuevo.")',
            block,
        )
        self.assertNotIn('/rest/v1/suscripciones', block)

    def test_trial_burn_patch_keeps_legacy_fail_soft_http_status_behavior(self):
        block = self.block
        self.assertIn('async with httpx.AsyncClient(timeout=10) as client:', block)
        self.assertIn('await client.patch(', block)
        self.assertIn('f"{SUPABASE_URL}/rest/v1/usuarios?id=eq.{user_id}"', block)
        self.assertIn('json={"trial_max_usado": True}', block)
        self.assertNotIn('await patch_rows(', block)
        self.assertLess(block.index('await post_rows('), block.index('await client.patch('))


if __name__ == "__main__":
    unittest.main()
