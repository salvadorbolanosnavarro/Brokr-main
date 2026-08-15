"""Dry-run guard for the first bounded main.py PostgREST migration."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_main_telemetry_writes import transform


ROOT = Path(__file__).resolve().parents[1]


class MainTelemetryCoreRefactorTests(unittest.TestCase):
    def test_transform_moves_only_telemetry_writes_to_core_and_compiles(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertNotEqual(source, updated)
        self.assertIn("from core.database import post_rows", updated)
        self.assertIn(
            'await post_rows(\n            "usage_logs", payload, prefer="return=minimal", timeout=6',
            updated,
        )
        self.assertIn(
            'await post_rows(\n            "module_sessions",',
            updated,
        )
        self.assertEqual(
            updated.count("/rest/v1/usage_logs"),
            source.count("/rest/v1/usage_logs") - 1,
        )
        self.assertEqual(
            updated.count("/rest/v1/module_sessions"),
            source.count("/rest/v1/module_sessions") - 1,
        )
        # Telemetry remains explicitly non-critical/fail-soft.
        self.assertIn("# TELEMETRÍA — uso de IA y tiempo por módulo", updated)
        self.assertIn('"""Inserta una fila en usage_logs. Fire-and-forget: nunca lanza."""', updated)
        self.assertIn("Silenciosamente ignora payloads inválidos o usuarios anónimos", updated)
        compile(updated, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
