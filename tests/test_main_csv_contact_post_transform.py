"""Dry-run guard for CSV-import new-contact POST Core routing."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SCRIPT = ROOT / "scripts" / "refactor_main_csv_contact_post_core.py"

spec = importlib.util.spec_from_file_location("csv_contact_post_transform", SCRIPT)
transform = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(transform)


class MainCsvContactPostTransformTests(unittest.TestCase):
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

    def test_status_caches_and_transport_contract_are_preserved(self):
        new = transform.NEW
        self.assertIn('await post_rows(', new)
        self.assertIn('"contactos"', new)
        self.assertIn('nuevo,', new)
        self.assertIn('prefer="return=minimal"', new)
        self.assertIn('timeout=20', new)
        self.assertIn('accepted_statuses=(200, 201, 204)', new)
        self.assertIn('importados += 1', new)
        self.assertIn('contacto_id = nuevo["id"]', new)
        self.assertIn('por_tel[tel] = {"id": contacto_id, **m}', new)
        self.assertIn('por_email[email] = {"id": contacto_id, **m}', new)
        self.assertIn('except httpx.HTTPStatusError:\n                    errores += 1\n                    continue', new)
        self.assertNotIn('except Exception', new)
        self.assertNotIn('/rest/v1/', new)


if __name__ == "__main__":
    unittest.main()
