"""Permanent guard for CSV-import new-contact POST Core routing."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainCsvContactPostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.post("/contactos/importar-archivo")')
        end = cls.source.index('\n\n# ════════════════════════════════════════════════════════════════\n# Migración completa EasyBroker', start)
        cls.block = cls.source[start:end]

    def test_new_contact_post_uses_core_with_exact_legacy_statuses(self):
        block = self.block
        self.assertIn('await post_rows(\n                        "contactos",', block)
        self.assertIn('nuevo,', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=20', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertNotIn('ri = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos"', block)

    def test_success_caches_and_http_failure_behavior_are_preserved(self):
        block = self.block
        self.assertIn('importados += 1', block)
        self.assertIn('contacto_id = nuevo["id"]', block)
        self.assertIn('por_tel[tel] = {"id": contacto_id, **m}', block)
        self.assertIn('por_email[email] = {"id": contacto_id, **m}', block)
        self.assertIn('except httpx.HTTPStatusError:\n                    errores += 1\n                    continue', block)
        self.assertIn('await post_rows(\n                        "contactos_propiedades",', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertIn('vinculos_nuevos += 1', block)
        self.assertIn('pares_existentes.add((contacto_id, propiedad_id))', block)
        self.assertIn('except httpx.HTTPStatusError:\n                    pass', block)
        self.assertNotIn('rv = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', block)


if __name__ == "__main__":
    unittest.main()
