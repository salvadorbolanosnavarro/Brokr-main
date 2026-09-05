"""Permanent guards for legacy trial policies centralized in Core.

The one-time seven-day Broquer Max gift (``trial_max_available`` and the
``POST /subscription/trial-max`` endpoint that granted it) was removed —
Broquer no longer offers a no-card trial to new accounts. The expiry
machinery below stays: a "trialing" subscription created before the trial
was retired must still run out on its own ``trial_hasta`` instead of being
cut off mid-way.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "subscriptions.py"


class CoreSubscriptionTrialPoliciesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CORE.read_text(encoding="utf-8")

    def test_trial_grant_was_removed(self):
        s = self.source
        self.assertNotIn("async def trial_max_available(", s)
        self.assertNotIn("trial_max_usado", s)

    def test_trial_expiration_parser_preserves_legacy_fail_soft(self):
        s = self.source
        self.assertIn("def trial_has_expired(trial_hasta) -> bool:", s)
        self.assertIn('datetime.fromisoformat(str(trial_hasta).replace("Z", "+00:00")) <= datetime.now(timezone.utc)', s)
        self.assertIn('except Exception:\n        return False', s)

    def test_expiration_persistence_is_best_effort(self):
        s = self.source
        self.assertIn("async def expire_trial_subscription(sub_id) -> None:", s)
        self.assertIn('"status": "expired"', s)
        self.assertIn('timeout=8', s)
        self.assertIn('except Exception:\n        pass', s)

    def test_core_compiles(self):
        compile(self.source, "core/subscriptions.py", "exec")


if __name__ == "__main__":
    unittest.main()
