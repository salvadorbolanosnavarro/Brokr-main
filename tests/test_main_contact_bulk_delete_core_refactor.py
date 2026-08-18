"""Regression guard for contact bulk database routing through Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainContactBulkDeleteCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_contact_bulk_operation_uses_bounded_core_chunks(self):
        source = self.source
        self.assertIn('for i in range(0, len(ids_reales), 200):', source)
        self.assertIn('await delete_rows(\n                        "contactos",', source)
        self.assertIn('{**filtro, "id": f"in.({lista})"}', source)
        self.assertIn('prefer="return=minimal"', source)
        self.assertIn('timeout=60', source)
        self.assertIn('accepted_statuses=(200, 204)', source)
        self.assertIn('eliminados += len(lote)', source)
        self.assertNotIn('f"{SUPABASE_URL}/rest/v1/contactos"', source)

    def test_http_rejections_remain_per_chunk_fail_soft(self):
        marker = 'await delete_rows(\n                        "contactos",'
        start = self.source.index(marker)
        block = self.source[start:start + 700]
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertIn('pass', block)
        self.assertNotIn('except Exception:', block)


if __name__ == "__main__":
    unittest.main()
