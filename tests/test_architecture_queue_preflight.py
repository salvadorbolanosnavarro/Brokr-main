import unittest

from scripts.apply_architecture_queue import STEPS, preflight


class ArchitectureQueuePreflightTests(unittest.TestCase):
    def test_every_prepared_transform_composes_in_order_without_writing(self):
        staged = preflight()
        self.assertGreaterEqual(len(STEPS), 40)
        names = [step.name for step in STEPS]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(staged)
        target_names = {path.name for path in staged}
        self.assertIn("main.py", target_names)
        self.assertIn("whatsapp.py", target_names)

    def test_destructive_steps_are_source_transforms_only(self):
        names = [step.name for step in STEPS]
        self.assertIn("self-account-delete-static", names)
        self.assertIn("whatsapp-delete-static", names)
        for step in STEPS:
            self.assertTrue(step.module.startswith("scripts.refactor_"))


if __name__ == "__main__":
    unittest.main()
