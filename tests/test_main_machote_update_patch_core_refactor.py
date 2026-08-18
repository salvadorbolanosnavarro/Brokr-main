"""Permanent guard for machote update PATCH Core routing."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "machotes.py"


class MainMachoteUpdatePatchCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROUTER.read_text(encoding="utf-8")
        start = cls.source.index('@router.patch("/contrato/machote/{machote_id}")')
        end = cls.source.index('\n\ndef _aplicar_fijos(', start)
        cls.block = cls.source[start:end]

    def test_update_patch_uses_core_and_scoped_filters(self):
        block = self.block
        self.assertIn('rows = await patch_rows(', block)
        self.assertIn('"machotes_contrato"', block)
        self.assertIn('{"id": f"eq.{machote_id}", "user_id": f"eq.{user_id}"}', block)
        self.assertIn('parche,', block)
        self.assertIn('prefer="return=representation"', block)
        self.assertIn('timeout=15', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertNotIn('/rest/v1/machotes_contrato', block)

    def test_http_empty_result_and_transport_contract_are_preserved(self):
        block = self.block
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertEqual(block.count('detail="No se pudieron guardar los cambios."'), 2)
        self.assertIn('if not rows:', block)
        self.assertIn('return rows[0]', block)
        segment = block[block.index('rows = await patch_rows('):]
        self.assertNotIn('except Exception', segment)


if __name__ == "__main__":
    unittest.main()
