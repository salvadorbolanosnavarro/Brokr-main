"""Permanent guard for best-effort trial-expiry PATCH Core routing."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "subscriptions.py"
MAIN = ROOT / "main.py"


class MainTrialExpiryPatchCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = CORE.read_text(encoding="utf-8")
        cls.main = MAIN.read_text(encoding="utf-8")

    def test_expiry_patch_delegates_to_core(self):
        fn = self.core
        self.assertIn('async def expire_trial_subscription(sub_id) -> None:', fn)
        self.assertIn('await patch_rows(', fn)
        self.assertIn('"suscripciones"', fn)
        self.assertIn('{"id": f"eq.{sub_id}"}', fn)
        self.assertIn('"status": "expired"', fn)
        self.assertIn('datetime.utcnow().isoformat()', fn)
        self.assertIn('timeout=8', fn)
        self.assertNotIn('/rest/v1/suscripciones', fn)

    def test_best_effort_contract_stays_intact(self):
        fn = self.core
        self.assertIn('if not sub_id:\n        return', fn)
        self.assertIn('except Exception:\n        pass', fn)
        self.assertIn('expire_trial_subscription as _expirar_trial_suscripcion', self.main)
        self.assertNotIn('async def _expirar_trial_suscripcion(', self.main)
        compile(self.core, "core/subscriptions.py", "exec")
        compile(self.main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
