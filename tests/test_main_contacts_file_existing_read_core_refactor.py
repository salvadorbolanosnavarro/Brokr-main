"""Permanent guards for /contactos/importar-archivo existing-contact Core read."""
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

    def test_only_contact_writes_remain_direct(self):
        self.assertEqual(self.block.count('f"{SUPABASE_URL}/rest/v1/contactos",'), 2)

    def test_core_read_preserves_http_fallback_and_other_io(self):
        block = self.block
        self.assertIn('existentes = await get_rows(\n                "contactos",', block)
        self.assertIn('"limit": "10000"', block)
        self.assertIn('"select": "id,telefono,email,nombre,empresa,notas,fuente,probabilidad,calle,mpio,cp,wa,etiquetas,estatus"', block)
        self.assertIn("timeout=20", block)
        self.assertIn("except httpx.HTTPStatusError:\n            existentes = []", block)
        self.assertIn('propiedades_existentes = await get_rows(\n                "propiedades",', block)
        self.assertIn('vinculos_existentes = await get_rows(\n                "contactos_propiedades",', block)
        self.assertIn('rb = await client.patch(\n                        f"{SUPABASE_URL}/rest/v1/contactos"', block)
        self.assertIn('ri = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos"', block)
        self.assertIn('rv = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', block)


if __name__ == "__main__":
    unittest.main()
