"""Dry-run guards for /easybroker/migrar-fotos batch Core read."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_manual_photo_batch_read_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("manual_photo_batch_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainManualPhotoBatchReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self, source: str) -> str:
        start = source.index('@app.post("/easybroker/migrar-fotos")')
        end = source.index('\n\n# ════════════════════════════════════════════════════════════════', start)
        return source[start:end]

    def test_transform_compiles_and_removes_direct_batch_get(self):
        transformed = _load_transform()(self.source)
        block = self._block(transformed)
        self.assertNotIn('r = await client.get(f"{SUPABASE_URL}/rest/v1/propiedades"', block)
        compile(transformed, "main.py", "exec")

    def test_core_read_preserves_500_and_storage_patch_writes(self):
        block = self._block(_load_transform()(self.source))
        self.assertIn('filas = await get_rows("propiedades", params, timeout=30)', block)
        self.assertIn('except Exception:\n        raise HTTPException(status_code=500, detail="No se pudo leer el inventario.")', block)
        self.assertIn('ru = await client.post(\n                f"{SUPABASE_URL}/storage/v1/object/{_FOTOS_BUCKET}/{nombre}"', block)
        self.assertIn('rp = await client.patch(\n                    f"{SUPABASE_URL}/rest/v1/propiedades"', block)
        self.assertIn('"Prefer": "return=minimal"', block)


if __name__ == "__main__":
    unittest.main()
