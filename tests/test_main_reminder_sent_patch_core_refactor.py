"""Permanent guard for reminder-sent PATCH Core routing."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def async_function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(
        item for item in tree.body
        if isinstance(item, ast.AsyncFunctionDef) and item.name == name
    )
    return ast.get_source_segment(source, node) or ""


class MainReminderSentPatchCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.function = async_function_source(cls.source, "_revisar_recordatorios")

    def test_reminder_sent_patch_delegates_to_core(self):
        fn = self.function
        self.assertIn('await patch_rows(', fn)
        self.assertIn('"tareas"', fn)
        self.assertIn('{"id": f"eq.{t[\'id\']}"}', fn)
        self.assertIn('{"recordatorio_enviado": True}', fn)
        self.assertIn('timeout=15', fn)
        self.assertNotIn('/rest/v1/tareas', fn)

    def test_best_effort_warning_contract_stays_intact(self):
        fn = self.function
        self.assertIn('except Exception as e:', fn)
        self.assertIn('No se pudo marcar recordatorio_enviado de %s: %s', fn)
        self.assertIn('_recordatorios_log.warning(', fn)
        compile(self.source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
