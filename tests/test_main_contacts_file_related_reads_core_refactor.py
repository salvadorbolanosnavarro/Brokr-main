"""Permanent guards for /contactos/importar-archivo related property/link Core routing."""
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


class MainContactsFileRelatedReadsCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.router_source = ROUTER.read_text(encoding="utf-8")
        cls.block = _route_block(cls.source, cls.router_source)

    def test_main_compiles_and_direct_related_gets_and_contact_writes_are_gone(self):
        self.assertNotIn('r2 = await client.get(\n            f"{SUPABASE_URL}/rest/v1/propiedades"', self.block)
        self.assertNotIn('r3 = await client.get(\n            f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', self.block)
        self.assertNotIn('rb = await client.patch(\n                        f"{SUPABASE_URL}/rest/v1/contactos"', self.block)
        self.assertNotIn('ri = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos"', self.block)
        self.assertNotIn('rv = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', self.block)
        compile(self.source, "main.py", "exec")

    def test_core_reads_patch_and_posts_preserve_http_fallback_and_link_write(self):
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
        self.assertIn('await post_rows(\n                        "contactos_propiedades",', block)
        self.assertIn('{"user_id": user_id, "contacto_id": contacto_id,', block)
        self.assertIn('"propiedad_id": propiedad_id, "relacion": "interes"', block)
        self.assertGreaterEqual(block.count('accepted_statuses=(200, 201, 204)'), 2)
        self.assertIn('except httpx.HTTPStatusError:\n                    pass', block)


if __name__ == "__main__":
    unittest.main()
