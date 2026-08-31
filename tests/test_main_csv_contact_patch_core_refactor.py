"""Permanent guard for CSV-import existing-contact PATCH Core routing."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "contact_file_import.py"


class MainCsvContactPatchCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_source = MAIN.read_text(encoding="utf-8")
        cls.router_source = ROUTER.read_text(encoding="utf-8")
        cls.source = (
            cls.main_source
            if '@app.post("/contactos/importar-archivo")' in cls.main_source
            else cls.router_source
        )
        marker = 'existente.update(patch)'
        cls.assert_marker_count = cls.source.count(marker)
        pos = cls.source.index(marker)
        cls.block = cls.source[max(0, pos - 1400):pos + 600]

    def test_csv_contact_update_marker_remains_unique(self):
        self.assertEqual(self.assert_marker_count, 1)

    def test_patch_uses_core_with_exact_legacy_statuses(self):
        block = self.block
        self.assertIn('await patch_rows(', block)
        self.assertIn('"contactos"', block)
        self.assertIn('{"id": f"eq.{contacto_id}"}', block)
        self.assertIn('patch,', block)
        self.assertIn('timeout=20', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertNotIn('await client.patch(', block)

    def test_success_cache_and_http_failure_behavior_are_preserved(self):
        block = self.block
        self.assertIn('actualizados += 1', block)
        self.assertIn('existente.update(patch)', block)
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertIn('errores += 1', block)
        self.assertNotIn('except Exception', block)


if __name__ == "__main__":
    unittest.main()
