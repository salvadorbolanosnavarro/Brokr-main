"""Dry-run guards for /contactos/importar-archivo related property/link Core reads."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_contacts_file_related_reads_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("contacts_file_related_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainContactsFileRelatedReadsCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self, source: str) -> str:
        start = source.index('@app.post("/contactos/importar-archivo")')
        end = source.index('\n\n# ════════════════════════════════════════════════════════════════\n# Migración completa EasyBroker', start)
        return source[start:end]

    def test_transform_compiles_and_removes_only_related_gets(self):
        transformed = _load_transform()(self.source)
        block = self._block(transformed)
        self.assertNotIn('r2 = await client.get(\n            f"{SUPABASE_URL}/rest/v1/propiedades"', block)
        self.assertNotIn('r3 = await client.get(\n            f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', block)
        compile(transformed, "main.py", "exec")

    def test_core_reads_preserve_http_fallback_and_writes(self):
        block = self._block(_load_transform()(self.source))
        self.assertIn('propiedades_existentes = await get_rows(\n                "propiedades",', block)
        self.assertIn('"eb_public_id": "not.is.null"', block)
        self.assertIn('"select": "id,eb_public_id"', block)
        self.assertIn('"limit": "5000"', block)
        self.assertIn('except httpx.HTTPStatusError:\n            propiedades_existentes = []', block)
        self.assertIn('vinculos_existentes = await get_rows(\n                "contactos_propiedades",', block)
        self.assertIn('"select": "contacto_id,propiedad_id"', block)
        self.assertIn('"limit": "20000"', block)
        self.assertIn('except httpx.HTTPStatusError:\n            vinculos_existentes = []', block)
        self.assertIn('rb = await client.patch(\n                        f"{SUPABASE_URL}/rest/v1/contactos"', block)
        self.assertIn('ri = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos"', block)
        self.assertIn('rv = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', block)


if __name__ == "__main__":
    unittest.main()
