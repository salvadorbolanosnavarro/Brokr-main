"""Dry-run guard for machote row DELETE Core routing."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SCRIPT = ROOT / "scripts" / "refactor_main_machote_delete_core.py"

spec = importlib.util.spec_from_file_location("machote_delete_transform", SCRIPT)
transform = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(transform)


class MainMachoteDeleteTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.transformed = transform.transform_source(cls.source)

    def test_transform_is_exact_and_compiles(self):
        compile(self.transformed, "main.py", "exec")
        self.assertEqual(MAIN.read_text(encoding="utf-8"), self.source)
        self.assertEqual(self.transformed.count(transform.NEW), 1)
        self.assertNotIn(transform.OLD, self.transformed)
        if transform.OLD in self.source:
            self.assertEqual(self.source.count(transform.OLD), 1)
            self.assertEqual(self.transformed, self.source.replace(transform.OLD, transform.NEW, 1))
        else:
            self.assertEqual(self.source.count(transform.NEW), 1)
            self.assertEqual(self.transformed, self.source)

    def test_delete_contract_is_preserved(self):
        new = transform.NEW
        self.assertIn('await delete_rows(', new)
        self.assertIn('"machotes_contrato"', new)
        self.assertIn('{"id": f"eq.{machote_id}", "user_id": f"eq.{user_id}"}', new)
        self.assertIn('prefer="return=minimal"', new)
        self.assertIn('timeout=15', new)
        self.assertIn('accepted_statuses=(200, 204)', new)
        self.assertIn('except httpx.HTTPStatusError:', new)
        self.assertIn('detail="No se pudo eliminar el machote."', new)
        self.assertNotIn('/rest/v1/machotes_contrato', new)
        self.assertNotIn('except Exception', new)


if __name__ == "__main__":
    unittest.main()
