"""Dry-run guard for machote creation POST Core routing."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SCRIPT = ROOT / "scripts" / "refactor_main_machote_create_post_core.py"

spec = importlib.util.spec_from_file_location("machote_create_post_transform", SCRIPT)
transform = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(transform)


class MainMachoteCreatePostTransformTests(unittest.TestCase):
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

    def test_status_cleanup_error_and_transport_contract_are_preserved(self):
        new = transform.NEW
        self.assertIn('await post_rows(', new)
        self.assertIn('"machotes_contrato"', new)
        self.assertIn('fila,', new)
        self.assertIn('prefer="return=representation"', new)
        self.assertIn('timeout=60', new)
        self.assertIn('accepted_statuses=(200, 201)', new)
        self.assertIn('except httpx.HTTPStatusError as e:', new)
        self.assertIn('for p in (storage_path, storage_path_original):', new)
        self.assertIn('/storage/v1/object/{MACHOTES_BUCKET}/{p}', new)
        self.assertIn('e.response.text[:200]', new)
        self.assertNotIn('except Exception as e:', new)
        self.assertNotIn('/rest/v1/machotes_contrato', new)


if __name__ == "__main__":
    unittest.main()
