"""Permanent guard for machote row deletion routed through core.database."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainMachoteDeleteCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = MAIN.read_text(encoding="utf-8")
        start = source.index('@app.delete("/contrato/machote/{machote_id}")')
        end = source.index('\n\n# ── PDF GENERATION', start)
        cls.block = source[start:end]

    def test_row_delete_routes_through_core_with_exact_legacy_contract(self):
        block = self.block
        self.assertIn('await delete_rows(', block)
        self.assertIn('"machotes_contrato"', block)
        self.assertIn('{"id": f"eq.{machote_id}", "user_id": f"eq.{user_id}"}', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=15', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertIn('detail="No se pudo eliminar el machote."', block)
        self.assertNotIn('/rest/v1/machotes_contrato', block)

    def test_storage_cleanup_remains_best_effort_and_domain_local(self):
        block = self.block
        self.assertIn('/storage/v1/object/{MACHOTES_BUCKET}/{p}', block)
        self.assertIn('for p in (machote.get("storage_path"), machote.get("storage_path_original")):', block)
        self.assertIn('except Exception:\n                pass', block)
        self.assertLess(block.index('/storage/v1/object/{MACHOTES_BUCKET}/{p}'), block.index('await delete_rows('))


if __name__ == "__main__":
    unittest.main()
