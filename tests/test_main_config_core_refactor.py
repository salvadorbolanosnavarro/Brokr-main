"""Dry-run guard for the one-shot main.py configuration migration."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_main_config_core import transform


ROOT = Path(__file__).resolve().parents[1]


class MainConfigCoreRefactorTests(unittest.TestCase):
    def test_transform_is_exact_and_compiles(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertNotEqual(updated, source)
        self.assertNotIn("os.environ.get(", updated)
        self.assertNotIn("os.getenv(", updated)
        self.assertIn("SUPABASE_KEY      = settings.supabase_anon_key", updated)
        self.assertIn("SUPABASE_SERVICE_KEY = settings.supabase_service_key", updated)
        self.assertIn("EB_API_KEY       = settings.easybroker_api_key or _config.get", updated)
        self.assertIn("FB_APP_ID     = settings.legacy_main_fb_app_id", updated)
        compile(updated, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
