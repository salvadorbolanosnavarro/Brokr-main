"""Dry-run guards for property bulk-delete verification Core reads."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_property_bulk_delete_reads_core.py"
MAIN = ROOT / "main.py"


def _transform():
    spec = importlib.util.spec_from_file_location("property_bulk_delete_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainPropertyBulkDeleteReadsCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self, source: str) -> str:
        start = source.index('@app.post("/propiedades/eliminar-masivo")')
        end = source.index('\n\n@app.post("/contactos/eliminar-masivo")', start)
        return source[start:end]

    def test_transform_compiles_and_removes_only_verification_gets(self):
        transformed = _transform()(self.source)
        block = self._block(transformed)
        self.assertNotIn('client.get(f"{SUPABASE_URL}/rest/v1/propiedades"', block)
        compile(transformed, "main.py", "exec")

    def test_core_reads_preserve_delete_and_storage_cleanup(self):
        block = self._block(_transform()(self.source))
        self.assertIn('filas = await get_rows(', block)
        self.assertIn('filas.extend(await get_rows(', block)
        self.assertIn('"propiedades",', block)
        self.assertIn('"select": "id,fotos"', block)
        self.assertIn('timeout=60', block)
        self.assertIn('raise HTTPException(status_code=500, detail="No se pudo leer el inventario.")', block)
        self.assertIn('rd = await client.delete(\n                    f"{SUPABASE_URL}/rest/v1/propiedades"', block)
        self.assertIn('asyncio.create_task(_borrar_fotos_storage(nombres))', block)


if __name__ == "__main__":
    unittest.main()
