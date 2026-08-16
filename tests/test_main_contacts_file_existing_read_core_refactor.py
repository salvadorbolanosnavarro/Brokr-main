"""Dry-run guards for /contactos/importar-archivo existing-contact Core read."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_contacts_file_existing_read_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("contacts_file_existing_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainContactsFileExistingReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self, source: str) -> str:
        start = source.index('@app.post("/contactos/importar-archivo")')
        end = source.index('\n\n# ════════════════════════════════════════════════════════════════\n# Migración completa EasyBroker', start)
        return source[start:end]

    def test_transform_compiles_and_removes_only_existing_contact_get(self):
        transformed = _load_transform()(self.source)
        block = self._block(transformed)
        self.assertEqual(block.count('f"{SUPABASE_URL}/rest/v1/contactos",'), 2)
        compile(transformed, "main.py", "exec")

    def test_core_read_preserves_http_fallback_and_other_io(self):
        block = self._block(_load_transform()(self.source))
        self.assertIn('existentes = await get_rows(\n                "contactos",', block)
        self.assertIn('"limit": "10000"', block)
        self.assertIn('"select": "id,telefono,email,nombre,empresa,notas,fuente,probabilidad,calle,mpio,cp,wa,etiquetas,estatus"', block)
        self.assertIn("timeout=20", block)
        self.assertIn("except httpx.HTTPStatusError:\n            existentes = []", block)
        self.assertIn('r2 = await client.get(\n            f"{SUPABASE_URL}/rest/v1/propiedades"', block)
        self.assertIn('r3 = await client.get(\n            f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', block)
        self.assertIn('rb = await client.patch(\n                        f"{SUPABASE_URL}/rest/v1/contactos"', block)
        self.assertIn('ri = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos"', block)


if __name__ == "__main__":
    unittest.main()
