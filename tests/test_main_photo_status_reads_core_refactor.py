"""Dry-run guards for background/pending photo Core reads."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_photo_status_reads_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("photo_status_reads_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainPhotoStatusReadsCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self, source: str) -> str:
        start = source.index("async def _migrar_fotos_org(org_id: str):")
        end = source.index('\n\n@app.post("/easybroker/migrar-fotos")', start)
        return source[start:end]

    def test_transform_compiles_and_removes_two_direct_reads(self):
        transformed = _load_transform()(self.source)
        block = self._block(transformed)
        self.assertNotIn('r = await client.get(f"{SUPABASE_URL}/rest/v1/propiedades"', block)
        compile(transformed, "main.py", "exec")

    def test_worker_and_pending_reads_use_core_but_patch_remains_direct(self):
        block = self._block(_load_transform()(self.source))
        self.assertIn('filas = await get_rows("propiedades", params, timeout=30.0)', block)
        self.assertIn('except Exception:\n                    break', block)
        self.assertIn('filas_pendientes = await get_rows(\n            "propiedades",', block)
        self.assertIn('{"org_id": f"eq.{org_id}", "select": "fotos"}', block)
        self.assertIn('timeout=30', block)
        self.assertIn('except Exception:\n        pass', block)
        self.assertIn('await client.patch(\n                            f"{SUPABASE_URL}/rest/v1/propiedades"', block)
        self.assertIn('"Prefer": "return=minimal"', block)


if __name__ == "__main__":
    unittest.main()
