"""Permanent guards for legacy trial policies centralized in Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "subscriptions.py"


class CoreSubscriptionTrialPoliciesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CORE.read_text(encoding="utf-8")

    def test_trial_availability_remains_fail_closed_and_one_time(self):
        s = self.source
        self.assertIn("async def trial_max_available(user_id: str) -> bool:", s)
        self.assertIn('"trial_max_usado"', s)
        self.assertIn('"suscripciones"', s)
        self.assertIn('return not subscriptions', s)
        self.assertIn('except Exception:\n        return False', s)
        self.assertIn('get_service_json_or_empty', s)

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
