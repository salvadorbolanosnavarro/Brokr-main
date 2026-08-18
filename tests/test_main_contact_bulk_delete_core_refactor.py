"""Regression guard for contact bulk database routing through Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "bulk_delete.py"


class MainContactBulkDeleteCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROUTER.read_text(encoding="utf-8")
        start = cls.source.index('@router.post("/contactos/eliminar-masivo")')
        cls.block = cls.source[start:]

    def test_contact_bulk_operation_uses_bounded_core_chunks(self):
        block = self.block
        self.assertIn('for i in range(0, len(ids_reales), 200):', block)
        self.assertIn('await delete_rows(', block)
        self.assertIn('"contactos"', block)
        self.assertIn('{**filtro, "id": f"in.({lista})"}', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=60', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertIn('eliminados += len(lote)', block)
        self.assertNotIn('/rest/v1/contactos', block)

    def test_http_rejections_remain_per_chunk_fail_soft_and_transport_hits_outer_500(self):
        block = self.block
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertIn('detail="No se pudieron borrar todos los contactos."', block)


if __name__ == "__main__":
    unittest.main()
