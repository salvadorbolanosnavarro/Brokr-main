"""Permanent guard for the extracted property bulk-delete implementation."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "bulk_delete.py"


class MainPropertyBulkDeleteTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_property_bulk_delete_is_extracted_and_compiles(self):
        self.assertNotIn('@app.post("/propiedades/eliminar-masivo")', self.main)
        self.assertIn('@router.post("/propiedades/eliminar-masivo")', self.router)
        self.assertIn('from routers.bulk_delete import router as bulk_delete_router', self.main)
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/bulk_delete.py", "exec")

    def test_partial_success_and_transport_contract_are_preserved(self):
        new = self.router
        self.assertIn('await delete_rows(', new)
        self.assertIn('"propiedades"', new)
        self.assertIn('{**filtro, "id": f"in.({lista})"}', new)
        self.assertIn('prefer="return=minimal"', new)
        self.assertIn('timeout=60', new)
        self.assertIn('accepted_statuses=(200, 204)', new)
        self.assertIn('eliminadas += len(lote)', new)
        self.assertIn('except httpx.HTTPStatusError:', new)
        self.assertNotIn('/rest/v1/propiedades', new)


if __name__ == "__main__":
    unittest.main()
