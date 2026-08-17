"""Permanent guards for Lead Ads contact-dedup Core delegation."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainFbLeadContactLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index("async def _fb_procesar_lead(valor: dict) -> None:")
        end = cls.source.index('\n\n@app.post("/facebook/leadgen/subscribe")', start)
        cls.block = cls.source[start:end]

    def test_only_new_contact_post_remains_direct(self):
        self.assertEqual(self.block.count("/rest/v1/contactos"), 1)
        self.assertIn('rc = await client.post(\n                f"{SUPABASE_URL}/rest/v1/contactos"', self.block)

    def test_lookup_and_existing_contact_patch_use_core_while_post_stays_direct(self):
        block = self.block
        self.assertIn('filas_existentes = await get_rows(\n                    "contactos",', block)
        self.assertIn("filtro,\n                    timeout=15", block)
        self.assertIn("except httpx.HTTPStatusError:\n                filas_existentes = []", block)
        self.assertIn("existente = filas_existentes[0] if filas_existentes else None", block)
        self.assertIn('await patch_rows(\n                        "contactos",', block)
        self.assertIn('{"id": f"eq.{existente[\'id\']}"}', block)
        self.assertIn('{"es_potencial": True, "updated_at": ahora}', block)
        self.assertIn('except httpx.HTTPStatusError:\n                    pass', block)
        self.assertIn('rc = await client.post(\n                f"{SUPABASE_URL}/rest/v1/contactos"', block)
        self.assertIn('await _anota({"error_detail": f"Error guardando el contacto: {e}"})', block)


if __name__ == "__main__":
    unittest.main()
