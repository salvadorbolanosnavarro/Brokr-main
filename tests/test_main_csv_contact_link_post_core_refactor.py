"""Permanent guard for CSV-import contact-property link POST Core routing."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainCsvContactLinkPostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.post("/contactos/importar-archivo")')
        end = cls.source.index('\n\n# ════════════════════════════════════════════════════════════════\n# Migración completa EasyBroker', start)
        cls.block = cls.source[start:end]

    def test_link_post_uses_core_with_exact_legacy_statuses(self):
        block = self.block
        self.assertIn('await post_rows(\n                        "contactos_propiedades",', block)
        self.assertIn('"contacto_id": contacto_id', block)
        self.assertIn('"propiedad_id": propiedad_id', block)
        self.assertIn('"relacion": "interes"', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=20', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertNotIn('rv = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', block)

    def test_success_cache_and_http_fail_soft_are_preserved(self):
        block = self.block
        self.assertIn('vinculos_nuevos += 1', block)
        self.assertIn('pares_existentes.add((contacto_id, propiedad_id))', block)
        self.assertIn('except httpx.HTTPStatusError:\n                    pass', block)
        self.assertIn('if (contacto_id, propiedad_id) in pares_existentes:\n                    continue', block)


if __name__ == "__main__":
    unittest.main()
