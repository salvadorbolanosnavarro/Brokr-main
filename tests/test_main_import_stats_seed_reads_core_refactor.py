"""Dry-run guards for EasyBroker import-stats seed Core reads."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_import_stats_seed_reads_core.py"
MAIN = ROOT / "main.py"


def _transform():
    spec = importlib.util.spec_from_file_location("import_stats_seed_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainImportStatsSeedReadsCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self, source: str) -> str:
        start = source.index('@app.post("/easybroker/import-stats")')
        end = source.index('\n\n@app.', start + 1)
        return source[start:end]

    def test_transform_compiles_and_removes_three_direct_seed_gets(self):
        transformed = _transform()(self.source)
        block = self._block(transformed)
        self.assertNotIn('f"{SUPABASE_URL}/rest/v1/propiedades"', block)
        self.assertNotIn('f"{SUPABASE_URL}/rest/v1/contactos"', block)
        self.assertNotIn('f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', block)
        compile(transformed, "main.py", "exec")

    def test_core_reads_preserve_fail_soft_and_writes(self):
        block = self._block(_transform()(self.source))
        self.assertIn('propiedades_importadas = await get_rows(', block)
        self.assertIn('existentes = await get_rows(', block)
        self.assertIn('vinculos_existentes = await get_rows(', block)
        self.assertGreaterEqual(block.count('except httpx.HTTPStatusError:'), 3)
        self.assertIn('ri = await client.post(\n                f"{SUPABASE_URL}/rest/v1/contactos"', block)
        self.assertIn('rp = await client.patch(\n                f"{SUPABASE_URL}/rest/v1/contactos"', block)
        self.assertIn('rv = await client.post(\n                f"{SUPABASE_URL}/rest/v1/contactos_propiedades"', block)


if __name__ == "__main__":
    unittest.main()
