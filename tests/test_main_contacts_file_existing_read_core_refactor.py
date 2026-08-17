"""Permanent guards for /contactos/importar-archivo existing-contact Core database routing."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainContactsFileExistingReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.post("/contactos/importar-archivo")')
        end = cls.source.index('\n\n# ════════════════════════════════════════════════════════════════\n# Migración completa EasyBroker', start)
        cls.block = cls.source[start:end]

    def test_direct_contact_and_link_writes_are_gone(self):
        self.assertEqual(self.block.count('f"{SUPABASE_URL}/rest/v1/contactos",'), 0)
        self.assertNotIn('rb = await client.patch(\n                        f"{SUPABASE_URL}/rest/v1/contactos"', self.block)
        self.assertNotIn('ri = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos"', self.block)
        self.assertNotIn('rv = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', self.block)

    def test_core_read_patch_contact_post_and_link_post_preserve_contract(self):
        block = self.block
        self.assertIn('existentes = await get_rows(\n                "contactos",', block)
        self.assertIn('"limit": "10000"', block)
        self.assertIn('"select": "id,telefono,email,nombre,empresa,notas,fuente,probabilidad,calle,mpio,cp,wa,etiquetas,estatus"', block)
        self.assertIn("timeout=20", block)
        self.assertIn("except httpx.HTTPStatusError:\n            existentes = []", block)
        self.assertIn('propiedades_existentes = await get_rows(\n                "propiedades",', block)
        self.assertIn('vinculos_existentes = await get_rows(\n                "contactos_propiedades",', block)
        self.assertIn('await patch_rows(\n                            "contactos",', block)
        self.assertIn('{"id": f"eq.{contacto_id}"}', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertIn('await post_rows(\n                        "contactos",', block)
        self.assertIn('await post_rows(\n                        "contactos_propiedades",', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertIn('except httpx.HTTPStatusError:\n                    errores += 1\n                    continue', block)
        self.assertIn('except httpx.HTTPStatusError:\n                    pass', block)
        self.assertIn('vinculos_nuevos += 1', block)
        self.assertIn('pares_existentes.add((contacto_id, propiedad_id))', block)


if __name__ == "__main__":
    unittest.main()
