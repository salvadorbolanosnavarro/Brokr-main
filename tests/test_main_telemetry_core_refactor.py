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
        self.assertIn("from core.database import get_rows, post_rows", source)
        self.assertIn(
            'await post_rows(\n            "usage_logs", payload, prefer="return=minimal", timeout=6',
            source,
        )
        self.assertIn(
            'await post_rows(\n            "module_sessions",',
            source,
        )
        # Reporting reads for these tables are also delegated to Core now.
        self.assertNotIn("/rest/v1/usage_logs", source)
        self.assertNotIn("/rest/v1/module_sessions", source)

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
