"""Permanent guard for CSV-import contact-property link POST Core routing."""
from __future__ import annotations

from pathlib import Path
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "contact_file_import.py"


def _route_block(main_source: str, router_source: str) -> str:
    if '@app.post("/contactos/importar-archivo")' in main_source:
        start = main_source.index('@app.post("/contactos/importar-archivo")')
        end = main_source.index(
            '\n\n# ════════════════════════════════════════════════════════════════\n# Migración completa EasyBroker',
            start,
        )
        return main_source[start:end]
    start = router_source.index('    @router.post("/contactos/importar-archivo")')
    end = router_source.index('\n    return router', start)
    return textwrap.dedent(router_source[start:end])


class MainCsvContactLinkPostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.router_source = ROUTER.read_text(encoding="utf-8")
        cls.block = _route_block(cls.source, cls.router_source)

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
