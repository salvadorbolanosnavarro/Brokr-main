"""Permanent guard for Facebook entity ledger PATCH Core routing."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def core_database_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    return {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "core.database"
        for alias in node.names
    }


class MainFbEntityPatchCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self) -> str:
        start = self.source.index('async def _fb_actualizar_entidad')
        end = self.source.index('\n\n# ─── FACEBOOK OAUTH', start)
        return self.source[start:end]

    def test_direct_patch_stays_removed(self):
        block = self._block()
        self.assertNotIn('r = await client.patch(', block)
        self.assertIn('patch_rows', core_database_imports(self.source))
        compile(self.source, "main.py", "exec")

    def test_core_patch_preserves_best_effort_error_contract(self):
        block = self._block()
        self.assertIn('await patch_rows(', block)
        self.assertIn('_FB_TABLA_ENTIDADES,', block)
        self.assertIn('{"id": f"eq.{row_id}"}', block)
        self.assertIn('timeout=10', block)
        self.assertIn('except httpx.HTTPStatusError as e:', block)
        self.assertIn('_fb_tabla_falta(e.response)', block)
        self.assertIn('_fb_avisa_migracion("actualizar entidad", e.response)', block)
        self.assertIn('e.response.status_code', block)
        self.assertIn('(e.response.text or "")[:300]', block)
        self.assertIn('except Exception as e:', block)
        self.assertIn('_fb_log.error("Error actualizando %s: %s", _FB_TABLA_ENTIDADES, e)', block)


if __name__ == "__main__":
    unittest.main()
