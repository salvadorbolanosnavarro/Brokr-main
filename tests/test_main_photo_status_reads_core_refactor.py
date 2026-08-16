"""Permanent guards for background/pending photo Core reads."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainPhotoStatusReadsCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index("async def _migrar_fotos_org(org_id: str):")
        end = cls.source.index('\n\n@app.post("/easybroker/migrar-fotos")', start)
        cls.block = cls.source[start:end]

    def test_main_compiles_and_two_direct_reads_are_gone(self):
        self.assertNotIn('r = await client.get(f"{SUPABASE_URL}/rest/v1/propiedades"', self.block)
        compile(self.source, "main.py", "exec")

    def test_worker_and_pending_reads_use_core_but_patch_remains_direct(self):
        block = self.block
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
