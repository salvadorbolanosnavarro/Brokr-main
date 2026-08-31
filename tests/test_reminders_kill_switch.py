"""Permanent regression guard for the reminders-cycle environment kill switch."""
from __future__ import annotations

import importlib
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RemindersKillSwitchRegressionTests(unittest.TestCase):
    def test_router_guards_startup_before_creating_the_loop_task(self):
        source = (ROOT / "routers" / "reminders.py").read_text(encoding="utf-8")

        self.assertIn("from core.config import settings", source)

        startup_idx = source.index('@router.on_event("startup")')
        guard_idx = source.index("if not settings.reminders_enabled:", startup_idx)
        create_task_idx = source.index("asyncio.create_task(_recordatorios_loop())", startup_idx)

        self.assertGreater(guard_idx, startup_idx)
        self.assertGreater(create_task_idx, guard_idx)

    def test_reminders_enabled_defaults_to_true_when_unset(self):
        original_environ = dict(os.environ)
        try:
            os.environ.pop("RECORDATORIOS_ACTIVOS", None)
            import core.config as core_config

            core_config = importlib.reload(core_config)
            self.assertTrue(core_config.settings.reminders_enabled)
        finally:
            os.environ.clear()
            os.environ.update(original_environ)
            import core.config as core_config

            importlib.reload(core_config)

    def test_reminders_enabled_can_be_disabled_via_env(self):
        original_environ = dict(os.environ)
        try:
            os.environ["RECORDATORIOS_ACTIVOS"] = "false"
            import core.config as core_config

            core_config = importlib.reload(core_config)
            self.assertFalse(core_config.settings.reminders_enabled)
        finally:
            os.environ.clear()
            os.environ.update(original_environ)
            import core.config as core_config

            importlib.reload(core_config)


if __name__ == "__main__":
    unittest.main()
