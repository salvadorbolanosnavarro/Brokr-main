"""Permanent guards for /contactos/importar-archivo related property/link Core routing."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainContactsFileRelatedReadsCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.post("/contactos/importar-archivo")')
        end = cls.source.index('\n\n# ════════════════════════════════════════════════════════════════\n# Migración completa EasyBroker', start)
        cls.block = cls.source[start:end]

    def test_main_compiles_and_direct_related_gets_and_contact_writes_are_gone(self):
        self.assertNotIn('r2 = await client.get(\n            f"{SUPABASE_URL}/rest/v1/propiedades"', self.block)
        self.assertNotIn('r3 = await client.get(\n            f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', self.block)
        self.assertNotIn('rb = await client.patch(\n                        f"{SUPABASE_URL}/rest/v1/contactos"', self.block)
        self.assertNotIn('ri = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos"', self.block)
        compile(self.source, "main.py", "exec")

    def test_core_reads_patch_and_post_preserve_http_fallback_and_link_write(self):
        block = self.block
        self.assertIn('propiedades_existentes = await get_rows(\n                "propiedades",', block)
        self.assertIn('"eb_public_id": "not.is.null"', block)
        self.assertIn('"select": "id,eb_public_id"', block)
        self.assertIn('"limit": "5000"', block)
        self.assertIn('except httpx.HTTPStatusError:\n            propiedades_existentes = []', block)
        self.assertIn('vinculos_existentes = await get_rows(\n                "contactos_propiedades",', block)
        self.assertIn('"select": "contacto_id,propiedad_id"', block)
        self.assertIn('"limit": "20000"', block)
        self.assertIn('except httpx.HTTPStatusError:\n            vinculos_existentes = []', block)
        self.assertIn('await patch_rows(\n                            "contactos",', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertIn('await post_rows(\n                        "contactos",', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertIn('rv = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', block)


if __name__ == "__main__":
    unittest.main()
