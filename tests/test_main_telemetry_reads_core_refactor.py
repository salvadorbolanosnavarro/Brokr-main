"""Dry-run guard for bounded main.py telemetry report reads migration."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_main_telemetry_reads import transform

ROOT = Path(__file__).resolve().parents[1]


class MainTelemetryReadsCoreRefactorTests(unittest.TestCase):
    def test_transform_moves_report_reads_to_core_and_preserves_fail_soft(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        updated = transform(source)
        self.assertIn("from core.database import get_rows, post_rows", updated)
        self.assertIn('usage_rows = await get_rows(\n            "usage_logs",', updated)
        self.assertIn('session_rows = await get_rows(\n            "module_sessions",', updated)
        self.assertNotIn("/rest/v1/usage_logs", updated)
        self.assertNotIn("/rest/v1/module_sessions", updated)
        self.assertIn("except Exception:\n        usage_rows = []", updated)
        self.assertIn("except Exception:\n        session_rows = []", updated)
        self.assertIn('"limit": "20000"', updated)
        self.assertIn('"limit": "50000"', updated)
        compile(updated, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
