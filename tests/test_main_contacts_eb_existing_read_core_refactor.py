"""Dry-run guards for /contactos/importar-eb existing-contact Core read."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_contacts_eb_existing_read_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("contacts_eb_existing_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainContactsEbExistingReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self, source: str) -> str:
        start = source.index('@app.post("/contactos/importar-eb")')
        end = source.index('\n\n@app.post("/contactos/importar-archivo")', start)
        return source[start:end]

    def test_transform_compiles_and_removes_existing_contact_get(self):
        transformed = _load_transform()(self.source)
        block = self._block(transformed)
        self.assertNotIn('r_existing = await client.get(\n            f"{SUPABASE_URL}/rest/v1/contactos"', block)
        compile(transformed, "main.py", "exec")

    def test_core_read_preserves_fail_soft_and_writes(self):
        block = self._block(_load_transform()(self.source))
        self.assertIn('existing = await get_rows(\n            "contactos",', block)
        self.assertIn('"select": "id,telefono,email,nombre,empresa,notas,fuente,probabilidad,calle,mpio,cp,wa,etiquetas"', block)
        self.assertIn('timeout=15', block)
        self.assertIn('except httpx.HTTPStatusError:\n        existing = []', block)
        self.assertIn('rb = await client.patch(\n                        f"{SUPABASE_URL}/rest/v1/contactos?id=eq.{existente[\'id\']}&{filtro_patch}"', block)
        self.assertIn('ri = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos"', block)


if __name__ == "__main__":
    unittest.main()
