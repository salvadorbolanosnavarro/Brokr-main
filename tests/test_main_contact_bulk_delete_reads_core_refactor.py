"""Permanent guards for contact bulk-delete verification Core reads."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "bulk_delete.py"


class MainContactBulkDeleteReadsCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROUTER.read_text(encoding="utf-8")
        start = cls.source.index('@router.post("/contactos/eliminar-masivo")')
        cls.block = cls.source[start:]

    def test_direct_verification_gets_and_delete_stay_removed(self):
        self.assertNotIn('/rest/v1/contactos', self.block)

    def test_core_reads_and_delete_preserve_contract(self):
        block = self.block
        self.assertIn('filas = await get_rows(', block)
        self.assertIn('filas.extend(await get_rows(', block)
        self.assertIn('"contactos"', block)
        self.assertIn('"select": "id"', block)
        self.assertIn('timeout=60', block)
        self.assertIn('detail="No se pudo leer el directorio."', block)
        self.assertIn('await delete_rows(', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertIn('detail="No se pudieron borrar todos los contactos."', block)


if __name__ == "__main__":
    unittest.main()
