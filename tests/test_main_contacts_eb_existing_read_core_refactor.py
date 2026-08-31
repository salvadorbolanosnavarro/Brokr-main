"""Permanent guards for /contactos/importar-eb existing-contact Core read."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "easybroker_contact_import.py"


class MainContactsEbExistingReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = ROUTER.read_text(encoding="utf-8")

    def test_direct_existing_contact_get_stays_removed(self):
        self.assertNotIn('r_existing = await client.get(\n            f"{SUPABASE_URL}/rest/v1/contactos"', self.block)

    def test_core_database_io_preserves_fail_soft_and_write_contracts(self):
        block = self.block
        self.assertIn('existing = await get_rows(\n            "contactos",', block)
        self.assertIn('"select": "id,telefono,email,nombre,empresa,notas,fuente,probabilidad,calle,mpio,cp,wa,etiquetas"', block)
        self.assertIn('timeout=15', block)
        self.assertIn('except httpx.HTTPStatusError:\n        existing = []', block)
        self.assertIn('await patch_rows(\n                            "contactos",', block)
        self.assertIn('{"id": f"eq.{existente[\'id\']}", **filtro_patch}', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertNotIn('rb = await client.patch(', block)
        self.assertIn('await post_rows(\n                        "contactos",', block)
        self.assertIn('accepted_statuses=(200, 201)', block)
        self.assertNotIn('ri = await client.post(', block)
        self.assertNotIn('/rest/v1/contactos', block)


if __name__ == "__main__":
    unittest.main()
