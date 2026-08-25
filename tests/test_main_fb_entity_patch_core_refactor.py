"""Permanent guard for Facebook entity ledger PATCH Core routing."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "facebook_persistence.py"


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
        cls.core = CORE.read_text(encoding="utf-8")

    def _block(self) -> str:
        start = self.core.index('async def update_facebook_entity(')
        return self.core[start:]

    def test_direct_patch_stays_removed(self):
        block = self._block()
        self.assertNotIn('r = await client.patch(', block)
        self.assertIn('patch_rows', core_database_imports(self.core))
        self.assertNotIn('async def _fb_actualizar_entidad', self.source)
        self.assertIn('update_facebook_entity as _fb_actualizar_entidad', self.source)
        compile(self.source, "main.py", "exec")
        compile(self.core, "core/facebook_persistence.py", "exec")

    def test_core_patch_preserves_best_effort_error_contract(self):
        block = self._block()
        self.assertIn('await patch_rows(', block)
        self.assertIn('FACEBOOK_AD_ENTITIES_TABLE,', block)
        self.assertIn('{"id": f"eq.{row_id}"}', block)
        self.assertIn('timeout=10', block)
        self.assertIn('except httpx.HTTPStatusError as exc:', block)
        self.assertIn('facebook_table_missing(exc.response)', block)
        self.assertIn('warn_facebook_migration("actualizar entidad", exc.response)', block)
        self.assertIn('exc.response.status_code', block)
        self.assertIn('(exc.response.text or "")[:300]', block)
        self.assertIn('except Exception as exc:', block)
        self.assertIn('_log.error("Error actualizando %s: %s", FACEBOOK_AD_ENTITIES_TABLE, exc)', block)


if __name__ == "__main__":
    unittest.main()
