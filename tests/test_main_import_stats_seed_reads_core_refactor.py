"""Permanent guards for EasyBroker import-stats seed Core reads."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "easybroker_import_stats.py"


class MainImportStatsSeedReadsCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = ROUTER.read_text(encoding="utf-8")

    def test_three_direct_seed_gets_stay_removed(self):
        block = self.block
        self.assertNotIn('/rest/v1/propiedades', block)
        self.assertNotIn('/rest/v1/contactos', block)
        self.assertNotIn('/rest/v1/contactos_propiedades', block)

    def test_import_stats_database_io_is_core_routed_with_legacy_status_contracts(self):
        block = self.block
        self.assertIn('propiedades_importadas = await get_rows(', block)
        self.assertIn('existentes = await get_rows(', block)
        self.assertIn('vinculos_existentes = await get_rows(', block)
        self.assertGreaterEqual(block.count('except httpx.HTTPStatusError:'), 6)
        self.assertIn('await post_rows("contactos", chunk', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertIn('await patch_rows("contactos", {"id": f"in.({lista})"}', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertIn('await post_rows("contactos_propiedades", chunk', block)
        self.assertIn('except httpx.HTTPStatusError:\n                pass', block)


if __name__ == "__main__":
    unittest.main()
