"""Permanent guards for EasyBroker import-stats seed Core reads."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainImportStatsSeedReadsCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.post("/easybroker/import-stats")')
        end = cls.source.index('\n\n@app.', start + 1)
        cls.block = cls.source[start:end]

    def test_three_direct_seed_gets_stay_removed(self):
        block = self.block
        self.assertNotIn('r = await client.get(\n            f"{SUPABASE_URL}/rest/v1/propiedades"', block)
        self.assertNotIn('r2 = await client.get(\n            f"{SUPABASE_URL}/rest/v1/contactos"', block)
        self.assertNotIn('r3 = await client.get(\n            f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', block)

    def test_core_reads_and_contact_batch_post_preserve_fail_soft_and_other_writes(self):
        block = self.block
        self.assertIn('propiedades_importadas = await get_rows(', block)
        self.assertIn('existentes = await get_rows(', block)
        self.assertIn('vinculos_existentes = await get_rows(', block)
        self.assertGreaterEqual(block.count('except httpx.HTTPStatusError:'), 4)
        self.assertIn('await post_rows(\n                    "contactos",', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertNotIn('ri = await client.post(\n                f"{SUPABASE_URL}/rest/v1/contactos"', block)
        self.assertIn('rp = await client.patch(\n                f"{SUPABASE_URL}/rest/v1/contactos"', block)
        self.assertIn('rv = await client.post(\n                f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', block)


if __name__ == "__main__":
    unittest.main()
