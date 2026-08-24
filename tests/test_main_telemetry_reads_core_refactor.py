"""Permanent guards for admin usage telemetry reads delegated to Core."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "admin_usage.py"


def core_database_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    return {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "core.database"
        for alias in node.names
    }


class AdminUsageTelemetryReadsCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROUTER.read_text(encoding="utf-8")

    def test_report_reads_delegate_to_core_database(self):
        source = self.source
        self.assertIn("get_rows", core_database_imports(source))
        self.assertIn('usage_rows = await get_rows(\n            "usage_logs",', source)
        self.assertIn('session_rows = await get_rows(\n            "module_sessions",', source)
        self.assertNotIn("/rest/v1/usage_logs", source)
        self.assertNotIn("/rest/v1/module_sessions", source)
        self.assertIn('"limit": "20000"', source)
        self.assertIn('"limit": "50000"', source)

    def test_report_reads_remain_fail_soft(self):
        source = self.source
        self.assertIn("except Exception:\n        usage_rows = []", source)
        self.assertIn("except Exception:\n        session_rows = []", source)
        compile(source, "routers/admin_usage.py", "exec")


if __name__ == "__main__":
    unittest.main()
