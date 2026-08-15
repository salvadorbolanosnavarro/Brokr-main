"""Dry-run the exact admin webhook migration against the current source."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_admin_webhook import transform


ROOT = Path(__file__).resolve().parents[1]


class AdminWebhookRefactorTests(unittest.TestCase):
    def test_transform_matches_current_source_and_compiles(self):
        source = (ROOT / "admin_consola.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn("from core.webhooks import require_shared_secret", updated)
        self.assertIn("require_shared_secret(\n        request,", updated)
        self.assertNotIn("if CORREO_WEBHOOK_TOKEN:", updated)
        compile(updated, "admin_consola.py", "exec")


if __name__ == "__main__":
    unittest.main()
