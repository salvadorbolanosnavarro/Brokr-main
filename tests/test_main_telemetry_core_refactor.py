"""Permanent guards for main.py telemetry writes delegated to Core."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MainTelemetryCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "main.py").read_text(encoding="utf-8")

    def test_telemetry_writes_delegate_to_core_database(self):
        source = self.source
        self.assertIn("from core.database import post_rows", source)
        self.assertIn(
            'await post_rows(\n            "usage_logs", payload, prefer="return=minimal", timeout=6',
            source,
        )
        self.assertIn(
            'await post_rows(\n            "module_sessions",',
            source,
        )
        # Reads for telemetry reporting are intentionally a later bounded cut.
        self.assertEqual(source.count("/rest/v1/usage_logs"), 1)
        self.assertEqual(source.count("/rest/v1/module_sessions"), 1)

    def test_telemetry_remains_fail_soft(self):
        source = self.source
        self.assertIn("# TELEMETRÍA — uso de IA y tiempo por módulo", source)
        self.assertIn('"""Inserta una fila en usage_logs. Fire-and-forget: nunca lanza."""', source)
        self.assertIn("Silenciosamente ignora payloads inválidos o usuarios anónimos", source)
        self.assertIn(
            'await post_rows(\n            "usage_logs", payload, prefer="return=minimal", timeout=6\n        )\n    except Exception:\n        pass',
            source,
        )
        self.assertIn(
            'prefer="return=minimal",\n            timeout=5,\n        )\n    except Exception:\n        pass',
            source,
        )
        compile(source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
